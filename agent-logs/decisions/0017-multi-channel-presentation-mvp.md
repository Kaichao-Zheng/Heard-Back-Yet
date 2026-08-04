# 0017 Multi-channel Presentation MVP

## Status

Accepted

## Context

- 最终用户主要使用微信；面试仍需要可检查请求、错误与来源的 H5 参考客户端。
- 两个渠道的交互形式不同，但必须复用查询、上下文改写、回答生成和来源排序逻辑。
- `openclaw-weixin` 是依赖 OpenClaw 宿主的渠道插件。完整 OpenClaw 还会引入 Agent、Session、Prompt、工具和 OpenAI-compatible 协议，不是增加微信入口的最小依赖。

## Decision

- H5 作为主要展示、诊断和备用入口；Weixin Bot 作为第二个 Channel Adapter，仅验证文本问答、连续追问和来源 URL。
- 两个渠道调用同一 `POST /api/v1/responses`，消费同一 Canonical Response。请求使用可选应用层 `conversation_id`；不为微信新增 `/v1/chat/completions`。
- 默认不运行完整 OpenClaw。实现可替换的轻量 iLink Bridge，只负责扫码登录、长轮询、消息收发和传输状态。
- Web Renderer 展示完整响应；Weixin Renderer 确定性拼接 `answer` 与公开来源 URL，必要时拆分长消息，不再次调用模型。
- 接入 Bridge 前，将 `sources: list[dict[str, Any]]` 收紧为两个 Renderer 共用的 `SourceReference` 公共 schema。
- Weixin MVP 仅覆盖单账号、纯文本、白名单、cursor 持久化、去重、重连、长消息分段和公网来源 URL；不覆盖媒体、群聊、多账号、主动推送、富卡片或持久化记忆。
- iLink 的 bearer token、`context_token`、cursor 和重试属于必须实现的 transport 能力；媒体 AES/CDN 加解密因不支持媒体而暂不实现。
- 交付顺序为：H5、共享短时会话、Weixin Bridge、VPS/HTTPS/公网 evidence detail URL。实现沿用 `feat/weixin-access` 分支。

## Reasons

- H5 的 API、错误、来源和响应式布局更易检查，适合作为面试与诊断界面；微信更符合最终用户习惯。
- 轻量 Bridge 可隔离易变的渠道协议，并避免维护两套 Session/Memory 或把 HeardBackYet 伪装成通用 LLM。
- OpenAI compatibility 涉及完整的请求、鉴权、错误和流式协议；没有真实客户端需求时不扩大公共 contract。

## Consequences

- H5 与 Weixin 只能格式化同一 Canonical Response，不能各自改写查询或生成回答。
- Bridge 需独立测试扫码凭证、cursor、去重、重连和投递失败；这些 transport 状态不是对话 memory。
- 手机来源必须使用自有域名下的不透明公网 URL，不能暴露本地 `.eml` 路径。
- iLink 使用出站长轮询，无需微信回调域名或公网入站端口；协议变化时只替换 Bridge。

