# 0018 Ephemeral Conversation Boundary

## Status

Accepted

## Context

- H5 与 Weixin 都需要解析“那阿里呢”“为什么”等短时追问，但 MVP 不做持久化用户记忆。
- iLink 的 transport `session_id` 和 `context_token` 不是应用语义记忆，不能直接作为会话标识。

## Decision

- 保留 `AnswerQuery` 的无状态单轮路径；独立的 `ConversationService` 负责可选、有界、非持久化的会话协调，再调用 `AnswerQuery`。
- HTTP 请求可携带匿名 `conversation_id`。缺失时保持单轮行为；存在时读取上下文、改写追问并写回。它不是 Cookie、登录态或 transport session。
- `ConversationStore` 隔离存储实现。MVP 使用 `InMemoryConversationStore`：最近 3 个完整轮次、30 分钟滑动 TTL、最多 99 个会话，进程重启即丢失。
- `conversation_id` 最长 128 字符；用户问题和改写后问题最长 1000 字符。Store 在读写时惰性清理过期记录，最近 3 轮保存完整 Canonical Response。
- H5 在 `sessionStorage` 保存随机 ID；Bridge 用服务端密钥对 `bot_id + from_user_id` 做 HMAC，派生不透明 ID。原始微信用户 ID 不进入公共 HTTP contract。
- H5 与 Weixin 共用 FastAPI、`ConversationService` 和 Store。MVP 固定单 worker，并串行化同一会话的“读取 -> 执行 -> 写回”事务。
- 两个渠道默认是独立会话；跨渠道续聊依赖身份绑定，不属于 MVP。

## Reasons

- 短时指代消解需要服务端状态，但不要求设计长期记忆。
- 保留无状态 `AnswerQuery` 可继续服务 CLI、诊断、评测和单轮客户端，并保持 Response Layer 边界稳定。
- 统一 Store 可保证两个渠道使用相同 TTL、轮数、追问改写和 Canonical Response；port 使未来持久化不必重构渠道。

## Consequences

- 浏览器消息状态仅用于渲染，Bridge 仅负责传输；语义记忆以服务端 Store 为准。
- 进程重启或 TTL 到期后，会话视为新会话；无法解析的追问必须请求澄清。
- 单 worker 是内存 Store 的部署约束。多 worker 或多实例前必须改用 Redis/PostgreSQL 等共享存储，并提供并发控制。
- 会话协调、Store 与 `FollowUpRewriter` 位于 `heardbackyet/conversation/`；`heardbackyet/response/answer_query.py` 保持无状态；`heardbackyet/bootstrap.py` 负责组装。
