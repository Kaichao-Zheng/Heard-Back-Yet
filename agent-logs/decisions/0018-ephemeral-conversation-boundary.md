# 0018 Ephemeral Conversation boundary

## Status

Accepted

## Context

- 当前 `POST /api/v1/responses` 仅接收 `user_query`，核心 `AnswerQuery` 和 HTTP contract 都是单轮无状态的。
- H5 与 Weixin Bot 都需要最基础的短时连续对话，例如解析“那阿里呢”“为什么”“来源呢”等追问。
- MVP 短期内不实现持久化用户记忆；临时上下文仍必须由两个渠道复用，不能分别存放在浏览器和 Bridge 中。
- 微信 `context_token` 是当前回复的传输令牌，可能过期，不能充当应用语义记忆或稳定会话身份。

## Decision

- 保留现有无状态单轮路径，并在 Response Layer 外围增加可选、有界、非持久化的 `ConversationRunner`。
- 请求增加可选匿名 `conversation_id`：缺失时保持现有 `AnswerQuery.run(user_query)` 行为；存在时由 `ConversationRunner` 读取短时上下文、完成指代消解，再调用无状态 `AnswerQuery`。
- 临时状态通过 `ConversationStore` port 隔离。MVP 使用 `InMemoryConversationStore`；默认保存最近 3 轮和上一份 Canonical Response，TTL 为 30-60 分钟，进程重启即丢失。
- H5 在 `sessionStorage` 保存随机 UUID；Weixin Bridge 使用服务端密钥对 `bot_id + from_user_id` 做 HMAC，生成不透明 `conversation_id`。原始微信用户 ID 不进入公共 HTTP contract。
- H5 和 Weixin 调用同一个 FastAPI/ConversationRunner/Store。MVP 固定单 FastAPI worker，并对同一 `conversation_id` 使用异步锁，保证快速连续消息按顺序更新会话。
- 默认 H5 与 Weixin 是两个独立会话。跨渠道续聊依赖未来的身份绑定，不属于 MVP。

## Reasons

- “非持久化”与“无状态”不同；短时指代消解需要服务端暂存上下文，但不要求立即设计长期记忆模型。
- 保留无状态路径可继续服务 CLI、诊断、评测和单轮客户端，也避免会话能力侵入 `AnswerQuery` 的稳定输入边界。
- Store port 使持久化成为可替换实现，而不是渠道重构。
- 服务端统一存储可以保证 H5 与微信使用相同 TTL、轮数、上下文解析和 Canonical Response。

## Consequences

- 浏览器中的 `state.messages` 只负责渲染，Weixin Bridge 只负责传输；二者都不是语义记忆来源。
- FastAPI 进程重启或 TTL 到期后，已有 `conversation_id` 被视作新会话；无法解析的追问应请求澄清，不得猜测旧上下文。
- 多 worker 或多实例部署前必须将 Store 替换为 Redis/PostgreSQL，或提供可靠的共享状态与并发控制。
- 未来持久化只替换 `ConversationStore` 实现；H5、Weixin、`ConversationRunner` 和 `AnswerQuery` 的职责边界保持不变。
