# 0016 Presentation Layer boundary

## Status

Accepted

## Context

- 本阶段需要通过 FastAPI 暴露现有查询与回答链路，并接入最小前端
- HTTP 请求校验、响应序列化和 UI 展示属于 presentation 职责。
- 临时对话状态、约束继承和指代消解属于 query-to-response 工作流协调，
  不属于 HTTP 路由或前端组件。

## Decision

- 下一阶段命名为 `Presentation Layer`，只覆盖 FastAPI、公共 schema 和简陋前端。
- FastAPI 负责请求校验、调用框架无关的 query use case、HTTP 错误映射和响应序列化。
- 前端只负责输入、加载状态、回答与来源展示。
- Presentation 公共 contract 使用 `UserQueryRequest.user_query` 和 `UserQueryResponse`；
  `UserQueryService` 仅是 adapter port，不向下改写既有 contract。
- HTTP 使用自定义 `POST /api/v1/responses`。请求、响应、错误与状态语义均属于
  HeardBackYet，不复用 OpenAI `/v1/responses` 的精确路径或 `input` 字段，避免暗示
  OpenAI SDK compatibility。
- `response/` 定义框架无关的 Response Layer：`AnswerQuery` 作为公开工作流入口，
  协调 Query Orchestration 与内部 `ResponseGenerator`，供 presentation adapter 调用。
- `scripts.run_query` 保持 Orchestration 与 Response Generation 的显式人工集成入口，
  不经过产品级 `AnswerQuery`，避免后续 presentation 用例逻辑污染分层诊断。
- `app.py` 只负责 FastAPI composition、lifespan、runtime ownership、router 注册和
  全局异常映射；`routes.py` 只负责 endpoint 与 HTTP-to-workflow mapping；
  `schemas.py` 只负责公共 body contract。
- 成功 response 显式返回 `200`；因为不持久化 response resource，不使用 `201`。
  请求校验、未匹配 route、错误 method 与未预期异常分别映射为 `422/404/405/500`，
  并统一使用非敏感 `ErrorResponse` envelope。
- 第一版保持无状态；后续 decision `0018` 将临时 memory 提升为独立的 Conversation
  Coordination Layer，presentation 仍只传递匿名 session identifier。

## Reasons

- `Presentation Layer` 是 HTTP/API/UI 适配边界的通行名称，职责比 `Interaction Layer`
  更明确。
- 将 presentation 与框架无关的 query-to-response 工作流分离，避免 FastAPI 路由承担
  查询编排、回答生成、临时状态或领域规则。
- 完整目录名 `presentation` 比非标准缩写 `pres` 更易检索、理解和讲解。

## Consequences

- FastAPI app、routes 与 schema 放在 `heardbackyet/presentation/`。
- 公共 response endpoint 接收 `UserQueryRequest` 并返回 `UserQueryResponse`；内部 retrieval
  plan、provider API 形态和 workflow 类名不进入 URL。
- `AnswerQuery` 放在 `heardbackyet/response/answer_query.py`，作为 Response Layer 的
  框架无关入口；`response_generator.py` 保持为该层内部的回答生成组件。
- FastAPI 通过 `ConversationService` 调用 `AnswerQuery.run()` 并进入现有 Orchestrator；
  CLI eval 保持直接组装下层能力。
- 临时 memory 不属于 Presentation Layer；顶层 `bootstrap.py` 负责跨层依赖组装。
