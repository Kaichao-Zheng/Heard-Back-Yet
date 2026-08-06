"""Own dynamic iLink login, personal Bot pollers, and reply delivery."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from collections import deque
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import anyio
from wechat_clawbot.api.client import WeixinApiOptions
from wechat_clawbot.api.poll_core import poll_loop
from wechat_clawbot.api.types import GetUpdatesResp, MessageType
from wechat_clawbot.auth.accounts import DEFAULT_BASE_URL
from wechat_clawbot.auth.login_qr import (
    start_weixin_login_with_qr,
    wait_for_weixin_login,
)
from wechat_clawbot.messaging.inbound import body_from_item_list
from wechat_clawbot.messaging.send import send_message_weixin

from heardbackyet.presentation.weixin.config import WeixinSettings
from heardbackyet.presentation.weixin.renderer import render_weixin_messages


LOGGER = logging.getLogger(__name__)
QUERY_TOO_LONG_REPLY = "问题过长，请缩短到 1000 个字符以内后重试。"
SERVICE_ERROR_REPLY = "查询服务暂时不可用，请稍后重试。"


class QueryService(Protocol):
    def run(
        self,
        user_query: str,
        /,
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]: ...


class LoginCapacityReached(RuntimeError):
    pass


@dataclass
class _LoginSession:
    provider_session_key: str
    expires_at: float
    status: str = "waiting"
    task: asyncio.Task[None] | None = None


@dataclass(frozen=True)
class _AccountCredential:
    account_id: str
    account_key: str
    token: str
    base_url: str
    user_id: str


class WeixinRuntime:
    """Run personal iLink Bots inside the process-owned FastAPI lifespan."""

    def __init__(self, query_service: QueryService, settings: WeixinSettings) -> None:
        self._query_service = query_service
        self._settings = settings
        self._sessions: dict[str, _LoginSession] = {}
        self._accounts: dict[str, _AccountCredential] = {}
        self._poller_tasks: dict[str, asyncio.Task[None]] = {}
        self._poller_stop_events: dict[str, anyio.Event] = {}
        self._login_tasks: set[asyncio.Task[None]] = set()
        self._locks = tuple(asyncio.Lock() for _ in range(64))
        self._seen_ids: dict[str, deque[str]] = {}
        self._seen_id_sets: dict[str, set[str]] = {}

    async def start(self) -> None:
        await anyio.to_thread.run_sync(
            partial(self._accounts_dir.mkdir, parents=True, exist_ok=True)
        )
        credentials = await anyio.to_thread.run_sync(self._load_credentials)
        for credential in credentials:
            self._accounts[credential.account_key] = credential
            self._start_poller(credential)

    async def close(self) -> None:
        for stop_event in self._poller_stop_events.values():
            stop_event.set()
        tasks = [*self._login_tasks, *self._poller_tasks.values()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._login_tasks.clear()
        self._poller_tasks.clear()
        self._poller_stop_events.clear()

    @property
    def _accounts_dir(self) -> Path:
        return self._settings.state_dir / "accounts"

    def _credential_path(self, account_key: str) -> Path:
        return self._accounts_dir / f"{account_key}.json"

    @staticmethod
    def _account_key(account_id: str) -> str:
        digest = hashlib.sha256(account_id.encode("utf-8")).hexdigest()
        return f"bot_{digest[:32]}"

    @staticmethod
    def _is_https_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.netloc)

    def _load_credentials(self) -> list[_AccountCredential]:
        credentials: list[_AccountCredential] = []
        for path in self._accounts_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text("utf-8"))
                account_id = str(payload["accountId"]).strip()
                token = str(payload["token"]).strip()
                base_url = str(payload["baseUrl"]).strip()
                user_id = str(payload["userId"]).strip()
                if not all((account_id, token, base_url, user_id)):
                    raise ValueError("credential field is empty")
                if not self._is_https_url(base_url):
                    raise ValueError("credential base URL is not HTTPS")
                credentials.append(
                    _AccountCredential(
                        account_id=account_id,
                        account_key=self._account_key(account_id),
                        token=token,
                        base_url=base_url,
                        user_id=user_id,
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
                LOGGER.warning("Ignoring invalid Weixin credential file: %s", path.name)
        return credentials

    def _save_credential(self, credential: _AccountCredential) -> None:
        self._accounts_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "accountId": credential.account_id,
            "token": credential.token,
            "baseUrl": credential.base_url,
            "userId": credential.user_id,
        }
        path = self._credential_path(credential.account_key)
        temporary_path = path.with_suffix(f".{secrets.token_hex(6)}.tmp")
        temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        with contextlib.suppress(OSError):
            temporary_path.chmod(0o600)
        os.replace(temporary_path, path)

    def _remove_stale_credentials_for_user(self, credential: _AccountCredential) -> None:
        for account_key, existing in list(self._accounts.items()):
            if existing.user_id != credential.user_id or account_key == credential.account_key:
                continue
            self._stop_poller(account_key)
            self._accounts.pop(account_key, None)
            with contextlib.suppress(OSError):
                self._credential_path(account_key).unlink()
            with contextlib.suppress(OSError):
                (self._settings.state_dir / "sync" / f"{account_key}.json").unlink()

    def _stop_poller(self, account_key: str) -> None:
        stop_event = self._poller_stop_events.pop(account_key, None)
        if stop_event is not None:
            stop_event.set()
        task = self._poller_tasks.pop(account_key, None)
        if task is not None:
            task.cancel()

    def _purge_sessions(self) -> None:
        now = time.time()
        for session_id, session in list(self._sessions.items()):
            if session.status == "waiting" and now >= session.expires_at:
                session.status = "expired"
            if now - session.expires_at > 600:
                self._sessions.pop(session_id, None)

    async def start_login(self) -> str:
        self._purge_sessions()
        active_count = sum(
            1 for session in self._sessions.values() if session.status == "waiting"
        )
        if active_count >= self._settings.max_active_login_sessions:
            raise LoginCapacityReached

        result = await start_weixin_login_with_qr(DEFAULT_BASE_URL, force=True)
        if not result.qrcode_url or not self._is_https_url(result.qrcode_url):
            raise RuntimeError("iLink did not return a QR URL")

        internal_session_id = secrets.token_urlsafe(24)
        now = time.time()
        session = _LoginSession(
            provider_session_key=result.session_key,
            expires_at=now + self._settings.login_timeout_seconds,
        )
        self._sessions[internal_session_id] = session
        task = asyncio.create_task(self._complete_login(session))
        session.task = task
        self._login_tasks.add(task)
        task.add_done_callback(self._login_tasks.discard)
        return result.qrcode_url

    async def _complete_login(self, session: _LoginSession) -> None:
        try:
            result = await wait_for_weixin_login(
                session.provider_session_key,
                DEFAULT_BASE_URL,
                timeout_ms=self._settings.login_timeout_seconds * 1_000,
            )
            if not result.connected:
                session.status = "expired" if time.time() >= session.expires_at else "failed"
                return
            if not all((result.account_id, result.bot_token, result.base_url, result.user_id)):
                session.status = "failed"
                return
            if not self._is_https_url(result.base_url):
                session.status = "failed"
                return

            credential = _AccountCredential(
                account_id=result.account_id,
                account_key=self._account_key(result.account_id),
                token=result.bot_token,
                base_url=result.base_url,
                user_id=result.user_id,
            )
            self._remove_stale_credentials_for_user(credential)
            await anyio.to_thread.run_sync(self._save_credential, credential)
            self._stop_poller(credential.account_key)
            self._accounts[credential.account_key] = credential
            self._start_poller(credential)
            session.status = "connected"
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Weixin login session failed")
            session.status = "failed"

    def _start_poller(self, credential: _AccountCredential) -> None:
        existing = self._poller_tasks.get(credential.account_key)
        if existing is not None and not existing.done():
            return
        stop_event = anyio.Event()
        self._poller_stop_events[credential.account_key] = stop_event
        task = asyncio.create_task(self._poll_account(credential, stop_event))
        self._poller_tasks[credential.account_key] = task

    async def _poll_account(
        self,
        credential: _AccountCredential,
        stop_event: anyio.Event,
    ) -> None:
        async def process_response(response: GetUpdatesResp) -> None:
            for message in response.msgs or []:
                if message.message_type != MessageType.USER:
                    continue
                await self._process_inbound(
                    credential,
                    sender_id=message.from_user_id or "",
                    text=body_from_item_list(message.item_list),
                    context_token=message.context_token,
                    message_id=str(message.message_id or ""),
                )

        try:
            await poll_loop(
                account_id=credential.account_key,
                base_url=credential.base_url,
                token=credential.token,
                sync_buf_path=(
                    self._settings.state_dir
                    / "sync"
                    / f"{credential.account_key}.json"
                ),
                on_response=process_response,
                stop_event=stop_event,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Weixin account poller stopped unexpectedly")

    def _is_duplicate(self, account_key: str, message_id: str) -> bool:
        if not message_id:
            return False
        seen = self._seen_id_sets.setdefault(account_key, set())
        if message_id in seen:
            return True
        order = self._seen_ids.setdefault(account_key, deque())
        seen.add(message_id)
        order.append(message_id)
        while len(order) > 1_024:
            seen.discard(order.popleft())
        return False

    def _conversation_id(self, account_id: str, sender_id: str) -> str:
        identity = f"{account_id}\0{sender_id}".encode("utf-8")
        digest = hmac.new(
            self._settings.conversation_secret.encode("utf-8"),
            identity,
            hashlib.sha256,
        ).hexdigest()
        return f"wx_{digest[:48]}"

    async def _process_inbound(
        self,
        credential: _AccountCredential,
        *,
        sender_id: str,
        text: str,
        context_token: str | None,
        message_id: str,
    ) -> None:
        # An iLink Bot is bound 1:1 to its creator. Enforce the returned user ID
        # again before any private query reaches HeardBackYet.
        if not sender_id or sender_id != credential.user_id:
            LOGGER.warning("Rejected message whose sender does not own the iLink Bot")
            return
        if self._is_duplicate(credential.account_key, message_id):
            return
        query = text.strip()
        if not query:
            return

        conversation_id = self._conversation_id(credential.account_id, sender_id)
        stripe = int(hashlib.sha256(conversation_id.encode("ascii")).hexdigest(), 16)
        lock = self._locks[stripe % len(self._locks)]
        async with lock:
            if len(query) > 1_000:
                messages = (QUERY_TOO_LONG_REPLY,)
            else:
                try:
                    response = await anyio.to_thread.run_sync(
                        partial(
                            self._query_service.run,
                            query,
                            conversation_id=conversation_id,
                        )
                    )
                    messages = render_weixin_messages(
                        response,
                        max_chars=self._settings.max_reply_chars,
                    )
                except Exception:
                    LOGGER.exception("Weixin query processing failed")
                    messages = (SERVICE_ERROR_REPLY,)

            options = WeixinApiOptions(
                base_url=credential.base_url,
                token=credential.token,
                context_token=context_token,
            )
            for message in messages:
                try:
                    await send_message_weixin(sender_id, message, options)
                except Exception:
                    LOGGER.exception("Weixin reply delivery failed")
                    return
