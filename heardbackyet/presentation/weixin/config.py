"""Environment configuration for the in-process Weixin iLink channel."""

from __future__ import annotations

import contextlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path


MIN_SECRET_CHARS = 32
CONVERSATION_SECRET_FILENAME = "conversation-secret"


@dataclass(frozen=True)
class WeixinSettings:
    conversation_secret: str
    state_dir: Path
    login_timeout_seconds: int = 240
    max_active_login_sessions: int = 4
    max_reply_chars: int = 3_500

    @classmethod
    def from_env(cls) -> "WeixinSettings":
        state_dir_value = os.environ.get("HBY_WEIXIN_STATE_DIR", "").strip()
        state_dir = (
            Path(state_dir_value).expanduser()
            if state_dir_value
            else cls._default_state_dir()
        )
        configured_secret = os.environ.get(
            "HBY_WEIXIN_CONVERSATION_SECRET", ""
        ).strip()
        if configured_secret and len(configured_secret) < MIN_SECRET_CHARS:
            raise ValueError(
                "HBY_WEIXIN_CONVERSATION_SECRET must contain at least "
                f"{MIN_SECRET_CHARS} characters"
            )
        persisted_secret = cls._load_or_create_conversation_secret(
            state_dir,
            initial_secret=configured_secret or None,
        )
        conversation_secret = configured_secret or persisted_secret
        settings = cls(
            conversation_secret=conversation_secret,
            state_dir=state_dir,
            login_timeout_seconds=int(
                os.environ.get("HBY_WEIXIN_LOGIN_TIMEOUT_SECONDS", "240")
            ),
            max_active_login_sessions=int(
                os.environ.get("HBY_WEIXIN_MAX_ACTIVE_LOGINS", "4")
            ),
            max_reply_chars=int(os.environ.get("HBY_WEIXIN_MAX_REPLY_CHARS", "3500")),
        )
        settings.validate()
        return settings

    @staticmethod
    def _default_state_dir() -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if os.name == "nt" and local_app_data:
            return Path(local_app_data) / "HeardBackYet" / "weixin"
        return Path.home() / ".heardbackyet" / "weixin"

    @staticmethod
    def _load_or_create_conversation_secret(
        state_dir: Path,
        *,
        initial_secret: str | None = None,
    ) -> str:
        """Persist one stable HMAC key without exposing it to the browser."""
        state_dir.mkdir(parents=True, exist_ok=True)
        secret_path = state_dir / CONVERSATION_SECRET_FILENAME
        try:
            with secret_path.open("x", encoding="utf-8") as stream:
                secret = initial_secret or secrets.token_urlsafe(32)
                stream.write(secret)
            with contextlib.suppress(OSError):
                secret_path.chmod(0o600)
            return secret
        except FileExistsError:
            return secret_path.read_text("utf-8").strip()

    def validate(self) -> None:
        if len(self.conversation_secret) < MIN_SECRET_CHARS:
            raise ValueError(
                "HBY_WEIXIN_CONVERSATION_SECRET must contain at least "
                f"{MIN_SECRET_CHARS} characters"
            )
        if not 30 <= self.login_timeout_seconds <= 290:
            raise ValueError("HBY_WEIXIN_LOGIN_TIMEOUT_SECONDS must be between 30 and 290")
        if not 1 <= self.max_active_login_sessions <= 16:
            raise ValueError("HBY_WEIXIN_MAX_ACTIVE_LOGINS must be between 1 and 16")
        if self.max_reply_chars < 200:
            raise ValueError("HBY_WEIXIN_MAX_REPLY_CHARS must be at least 200")
