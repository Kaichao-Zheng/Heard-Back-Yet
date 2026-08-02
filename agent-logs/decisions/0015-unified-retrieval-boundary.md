# 0015 统一 Structured 与 Content Retrieval 边界

## Status

Accepted

## Context

- `RetrievalPlanner` 已使用 `StructuredRetrievalStep` 与 `SemanticRetrievalStep`
  表达两类执行路径，但实现分别位于并列的 `heardbackyet.query` 和
  `heardbackyet.retrieval` package。
- 顶层 `query` 同时指用户请求、`QuerySpec` 和底层数据库读取，增加了跨层沟通成本。
- 结构化数据库读取与 semantic、lexical、hybrid search 的共同职责都是按计划取回证据。

## Decision

- Retrieval 作为所有数据取回方式的统一下层边界，覆盖 structured、semantic、lexical
  和 hybrid retrieval。
- 删除 `heardbackyet.query` package；原 table/view reader 合并到
  `heardbackyet.retrieval.structured_retriever`。
- 可复用结构化读取函数从 `query_*` 改为 `retrieve_*`；SQL 仍是内部实现机制。
- Orchestration plan 参数统一为 `StructuredRetrievalParameters`，structured step id 与
  routing reason 也使用 retrieval 术语。
- `QuerySpec`、`QueryIntent` 和 `QueryOrchestrator` 保留在 Orchestration，因为它们表达
  顶层用户查询的理解、计划和协调，而不是底层数据访问。
- `scripts.query_applications` 暂时保留既有 CLI module 名称，避免破坏人工 workflow；其
  内部委托给 Structured Retrieval API。

## Reasons

- 物理 package 与既有 `RetrievalPlan` 类型体系保持一致，避免把 Structured Query
  误解为与 Retrieval 并列的架构层。
- `structured_retriever.py` 与 semantic、lexical、hybrid retriever 形成可见的平行关系。
- 保留 Query 的顶层业务语义，同时用 Retrieval 表达具体的证据获取方式。

## Consequences

- Decision 0011 中“structured step 委托给 `heardbackyet.query`”的实现位置被本决策取代；
  其 Planner/Executor、scope binding 和 fail-closed 原则继续有效。
- Orchestrator 与手工 CLI 的 import 路径和函数名需要同步更新，但 SQL、filter、排序与
  返回 record contract 不改变。
- 若未来需要重命名 `scripts.query_applications`，应作为单独的 CLI contract 变更处理。
