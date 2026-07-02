# 0005 Email Application Link Method

## Status

Accepted

## Context

- `application` 的 identity 是 `(company_id, position_id)`。
- 强关联要求 email 同时具备可映射的 company 和 position，才能写入 `email.application_id`。
- 实际数据中，assessment、interview 等状态邮件经常只有 company，没有 position，导致它们保存在 `email` 表但无法进入 application 时间线。
- 直接按 company 挂载会在同公司多岗位时造成误关联，并污染 `application.latest_status`。

## Decision

- `email.application_id` 允许三种关联来源：
  - `exact`: email 的 company 和 position 都通过 alias mapping 命中，强关联到 application。
  - `company_singleton`: email 属于 `APPLICATION_PROGRESS_LABELS`，company 可映射，position 缺失或未映射，且该 company 当前只有一个 application。
  - `manual`: 预留给未来人工确认后的关联。
- 新增 `email.application_link_method` 记录自动关联来源。
- 同 company 存在多个 application 时，不执行 company-only fallback，email 保持 `application_id = NULL`。
- auth、unrelated、delivery-failure 等非 progress label 不参与 fallback。

## Reasons

- `company_singleton` 的证据链弱于 `exact`，但在 company 当前只有一个 application 时，误挂风险可控。
- 显式记录 `application_link_method` 可以让后续查询、debug 和人工复核区分强关联与弱关联。
- 该策略提高状态邮件召回，避免大量只有 company 的 progress email 无法影响 application 时间线。
- 保持同公司多 application 不 fallback，避免把无法区分岗位的邮件静默挂到错误 application。

## Consequences

- `application.latest_status` 可能由 `company_singleton` 关联的 email 推导，因此查询状态时应同时查看来源 email 和 link method。
- 未来如果某 company 新增多个 application，需要能筛查历史 `company_singleton` 邮件进行人工复核。
- 后续如需更严格的审计，可扩展为人工 review 表或增加 manual link method。
