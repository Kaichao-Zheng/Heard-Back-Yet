# 0017 Multi-channel Presentation MVP

## Status

Accepted

## Context

- HeardBackYet 的最终用户 persona 是主要通过微信交流、很少主动使用浏览器的父母。
- 面试阶段仍需一个可完整检查请求、回答、错误和来源的参考客户端，并由开发者自己的微信完成通道验证。
- 微信聊天与 H5 的交互组件不同，但不应产生两套查询、Prompt、上下文改写、回答生成或来源排序逻辑。
- 腾讯当前主要通过 `openclaw-weixin` 插件公开并维护 iLink 微信通道；完整 OpenClaw runtime 超出本项目所需能力。

## Decision

- 展示层 MVP 按以下顺序交付：
  1. 本地 FastAPI + 移动优先 CSR/H5；
  2. 单账号、纯文本的 Weixin Bot 第二入口；
  3. 统一迁移到 VPS，并为 H5/API 配置域名与 HTTPS。
- H5 是面试的主要展示、Canonical Response 的完整参考客户端、诊断入口和微信故障时的备用入口。
- Weixin Bot 是同一服务的第二个 Channel Adapter；面试中只需简短但真实地证明文本问答、连续追问和来源 URL 输出。
- 两个渠道消费同一份 Canonical Response。Web Renderer 使用正文、状态、折叠来源和详情链接；Weixin Renderer 使用文本、编号来源和 URL，必要时确定性拆分长消息，不重新调用模型总结。
- Weixin 接入不运行完整 OpenClaw。实现可替换的轻量 Bridge，以腾讯公开的 iLink 协议和官方插件源码作为协议依据，负责扫码、长轮询、消息收发和传输状态，再调用 HeardBackYet 的统一服务。
- Weixin MVP 仅覆盖单账号、文本、白名单、cursor 持久化、消息去重、异常重连、长回答分段和公网来源 URL；排除语音、图片、文件、群聊、多账号、主动推送、富卡片和持久化记忆。
- 当前宽泛的 `sources: list[dict[str, Any]]` 后续应收紧为明确的 `SourceReference` 公共 schema，供两个 Renderer 确定性消费。

## Reasons

- H5 可使用浏览器 Network、Console 和 DOM 工具直接验证 API、错误状态、来源与响应式布局，调试链短于微信通道。
- 先稳定 Canonical Response，再接入微信，可以把业务工作流问题与 token、cursor、长轮询和消息投递问题分开。
- 父母的日常入口应尽量减少学习成本；微信适合最终交互，但不适合作为第一开发和诊断界面。
- 轻量 Bridge 能证明渠道扩展性，同时避免引入 OpenClaw 的 Agent、工具、会话和 Node runtime 作为业务依赖。

## Consequences

- H5 与 Weixin 只能格式化同一 response，不能各自改写查询或生成不同回答。
- 面试演示以 H5 为主；微信演示可直接输出完整公网 URL 列表，以较弱交互换取最小可靠范围。
- 本地 `.eml` 路径不能作为手机可打开来源；云端阶段可在自有域名提供不透明 evidence detail URL。
- iLink Bridge 是可替换的实验性 presentation adapter；腾讯协议或支持范围变化时，不影响 Response、Retrieval 或数据库层。
- 域名只服务 H5/API。Weixin Bridge 使用出站长轮询，不需要微信回调域名或公网入站端口。
