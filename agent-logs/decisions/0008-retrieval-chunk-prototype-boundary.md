# 0008 Retrieval Chunk Prototype Boundary

## Status

Accepted

## Context

- Query views 负责结构化事实和已关联 application evidence；未来还需要从 email 与 JD 文本中定位语义相关的 source。
- Semantic retrieval 需要覆盖符合条件但尚未链接 application 的 source，同时不能改变 evidence 的可信边界。
- 当前 corpus 较小，prototype 应避免多 chunk、增量版本和复杂索引生命周期。

## Decision

- 使用统一的 PostgreSQL `retrieval_chunk` 存储 email/JD rendered content、metadata 与 pgvector embedding。
- Prototype 采用 **context-enriched, single-chunk-per-source document strategy with deterministic truncation**：每个 source document 生成 0/1 个 chunk，不进行段落切分、滑动窗口或 overlap；不保存 chunk index、builder version 或 content hash，刷新时全量重建。
- `(source_type, source_id)` 唯一定位原始 source。Row 保存 nullable application/company/position identity、email classification、实际参与渲染的 `semantic_fields`、content、embedding model 和时间。
- `application_id` 允许为空；retrieval 命中 unlinked source 只表示文本相关，不自动提升为 application evidence。
- Email eligibility 包含 `applied`、`assessment`、`interview`、`offer`、`rejection`、`logistics`、`profile-update`；`auth`、`delivery-failure`、`unrelated`、`unknown` 不进入 corpus。
- JD 仅在至少一个 semantic field 有效时生成 chunk。Email/JD content 使用固定字段顺序确定性渲染，以 canonical identity、extracted alias 和 source-specific semantic fields 丰富上下文，并设置有限文本预算。
- Missing sentinel 不进入结构化 content；canonical 与 extracted identity 相同时不重复。完整 source facts 留在源表中，通过 source identity hydrate。
- Prototype embedding column 使用 `VECTOR(1024)`，Python 侧必须校验输出维度。

## Reasons

- 单表让 email/JD 共享 search、filter 和 provenance contract，同时保留 source tables 作为事实来源。
- `logistics` 与 `profile-update` 虽不驱动 status，但仍包含申请行动信息，也能降低它们与 progress labels 互相错分造成的漏索引。
- Content 承担语义理解，metadata 承担精确过滤、聚合和调试。
- 单 chunk 与全量重建符合当前 corpus 和 prototype 规模。

## Consequences

- Email retrieval 继承分类结果；被排除 label 的相关邮件无法由当前 corpus 挽回。
- Polymorphic source reference 没有跨 source tables 的数据库外键保证，hydration 必须按 `source_type` 选择表。
- Renderer、embedding model 或维度变化时默认全量重建；维度变化还需同步修改 SQL schema。
- 改用 paragraph、window 或其他 multi-chunk strategy 属于 retrieval contract 变更，需要全量重建 corpus、重新评估 retrieval quality，并重新决定 chunk identity 与结果 hydration 契约。
- Distance metric、threshold 与 ANN index 留给 search implementation 和 evaluation 决定。
