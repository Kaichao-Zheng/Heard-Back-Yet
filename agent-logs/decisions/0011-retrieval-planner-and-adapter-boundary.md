# 0011 Retrieval Planner 与 Adapter 边界

## Status

Accepted

## Context

- Structured query 与 semantic retrieval 已分别提供稳定的查询函数和 `SearchRequest` / `SearchFilters` contract。
- 用户问题进入 retrieval 前仍需要把已识别的 intent、entity 和候选约束转换成 structured、semantic 或 hybrid 执行步骤。
- Company 文本不能直接成为 vector metadata filter；hybrid 查询需要先通过 structured query 解析 canonical `company_id`，再把结果绑定到 semantic filter。
- 当前阶段只实现 planning 与 execution integration，不把自然语言 intent recognition 混入 Planner。

## Decision

- 新增 `heardbackyet.orchestration`，以 `query_spec.py` 中的 `QueryIntent` / `QuerySpec` 表示 Query Analyzer 与 Planner 共享的标准化输入 contract，以 `RouteDecision` 表示 Planner 内部 routing policy 的可解释路径选择。
- `RetrievalPlanner.plan(QuerySpec)` 先应用确定性的 routing policy，再生成无副作用的 `RetrievalPlan`；调用方不构造或传入 `RouteDecision`，Planner 不访问数据库、不调用 embedding，也不重新识别 intent。
- Planner 支持 structured、filtered semantic 与 hybrid 三种 mode；实际基础 step 只有 `StructuredRetrievalStep` 和 `SemanticRetrievalStep`。
- Hybrid 定义为 structured step 的输出通过 `StepOutputRef` 绑定到后续 semantic hard filter，而不是第三套 retrieval backend。
- Company-scoped hybrid plan 使用 `resolve_company` structured step，对 canonical company name 和 `company_alias.raw_name` 做大小写不敏感的精确匹配，再把唯一 `company_id` 绑定到 semantic filter。
- Company resolution 不调用 LLM、不使用模糊结果静默猜测；零匹配或多个不同 `company_id` 均不放宽 filter，由执行阶段显式报错。
- 新增薄 `retrieval_adapter.execute_retrieval_plan()` 解释 plan：structured step 委托给 `heardbackyet.query`，semantic step 构造已有 `SearchRequest` 并委托给 `heardbackyet.retrieval`，可按 step 选择 source hydration。
- 文件使用 `query_spec.py`、`retrieval_planner.py` 与 `retrieval_adapter.py` 明确表达业务能力；Analyzer/Planner 共享的输入 contract 独立放在 `query_spec.py`，Planner 自有的 plan dataclass 与实现共同放在 `retrieval_planner.py`，不保留泛化的 `contracts.py`。
- `orchestration/__init__.py` 只保留 package docstring；调用方从具体能力模块显式导入，不维护重复的 barrel export 列表。
- Adapter 直接返回 `step_id -> records`，不增加 Executor 或 result wrapper class，也不维护通用 handler registry。
- Query Analyzer、自然语言回答生成与跨 step 结果表达不属于本次实现；routing policy 与 Planner 共同构成单一 planning boundary，不增加独立 Router 组件。
- 本 branch 不提交仅覆盖内部 Planner/Executor 形状的阶段性测试；Query Analyzer/Orchestrator 接通后从公开入口建立长期保留的 golden/integration tests。

## Reasons

- 最小可行性方面只保留两种基础 retrieval step、一个顺序执行器和必要的数据边界，不引入通用 DAG、repository、依赖注入框架或独立 contracts framework。
- 架构标准化方面明确区分 query understanding、retrieval planning、execution 与底层 backend；后续扩展 routing policy 或 Analyzer 时可复用现有边界，而不把自然语言逻辑写进 retrieval。
- 将 Query understanding、planning 和 execution 分开，同时把紧密耦合的 route selection 收进 Planner，可以单独测试 filter 转换和步骤依赖，避免自然语言识别结果直接触发不可审计的全库 semantic search，也减少调用方的装配胶水。
- Hybrid 复用现有 structured/semantic contract，避免在 orchestration 层复制 SQL、embedding 或 source hydration 逻辑。
- Company resolution 不加 `LIMIT 1`，可以在生成 hard filter 前发现 alias/canonical 数据冲突，避免静默绑定错误公司。
- Retrieval adapter 只承担 step sequencing、output binding 和 backend delegation，保留 query/retrieval 层作为事实查询与相似度检索的唯一实现位置。

## Consequences

- 本决策以 `heardbackyet.orchestration` 取代 Decision 0009 中为未来预留的 `heardbackyet.routing` package 名称；Decision 0009 的薄 CLI 与可复用应用边界原则继续有效。
- Planner 的调用方只需提供 `QuerySpec`；Planner 内部 routing policy 根据 intent 和 scope 选择 structured、semantic 或 hybrid，并把理由保留在 `RetrievalPlan`。
- 直接 semantic 可以使用 `source_types`、`email_types` 或已知 ID filters；带 company 文本但没有 canonical ID 的 content query 必须选择 hybrid。
- Company-scoped hybrid query 绑定 `company_id`，因此保留同公司多个 application/position；只有公司零匹配或多个 canonical ID 冲突时才产生 `RetrievalScopeError`。
- Executor 返回按 step 分组的结果并保留 plan；最终 result assembly 与自然语言 answer synthesis 可在其上层独立实现。
