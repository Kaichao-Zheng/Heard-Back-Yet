# 0007 Application Snapshots and Query Views

## Status

Accepted

## Context

- Stage 4 正在为常见申请追踪问题增加只读 query views。
- `v_application_overview` 的核心契约是一行代表一个 `application`，用于回答当前申请状态、当前岗位信息和可解释来源。
- `job_description` 表达的是岗位描述快照，而不是静态岗位文本；同一个 `application` 可以关联多份 JD 快照。
- 在新增 JD 快照时间前，代表 JD 的选择只能依赖 `jd_id DESC`，这会把导入顺序误当成业务时间。
- `application.latest_status`、`application.latest_status_received_at` 和 `application.latest_status_email_id` 是当前申请状态的 canonical snapshot。
- `application.latest_status_email_id` 是指向支撑当前状态的 email 的逻辑指针；为避免和 `email.application_id` 形成复杂循环 FK，当前不在数据库层强制为真实 FK。

## Decision

- 在 `job_description` 上保留 `captured_at`，记录 JD 快照被采集或记录的业务时间。
- 当需要为一个 application 选择代表 JD 快照时，使用 `captured_at DESC NULLS LAST, jd_id DESC` 作为稳定排序语义。
- `v_application_overview` 不从 email event stream 重新计算 latest status，而是消费 `application` 表上的当前状态快照。
- `v_application_overview` 展开 `application.latest_status_email_id` 指向的 evidence email，使当前状态的来源在查询结果中可读、可审计。
- `v_application_overview` 应包含 application identity、当前状态快照、状态 evidence email、以及代表 JD 快照四组字段：
  - identity：`application_id`、`company_id`、`position_id`、`company_name`、`position_name`。
  - status snapshot：`latest_status`、`latest_status_received_at`、`latest_status_email_id`。
  - status evidence：从 `latest_status_email_id` 指向的 email 展开 `email_type`、`received_at`、`subject` 等可读字段；如果实现中保留 `application_link_method`，它表达的是 evidence email 的关联来源。
  - JD snapshot：`latest_jd_id`、`jd_captured_at`、`jd_location_raw`、`jd_salary_raw`、`jd_source_url` 等代表 JD 快照字段。
- overview 中的 evidence email 字段只是解释 `application` 当前状态快照的来源，不代表重新计算出来的最新 email。
- overview 中的 JD 字段来自代表 JD 快照；如果实现维护 `application.latest_jd_id`，view 应直接消费该 snapshot pointer，而不是在 view 内重复做实时 JD 选择。
- `v_application_timeline` 负责列出所有已关联的 email events；`v_application_overview` 只展示当前状态快照和支撑该快照的 evidence。
- status snapshot 指针和事实表是否一致，交给初始化 view `v_inconsistent_status_snapshot` 检查，而不是在 overview view 中加入第二套实时推导逻辑。

## Reasons

- `captured_at` 明确表达 JD 快照的业务时间，避免继续把 `jd_id` 当作采集时间或业务时间的代理。
- 保留 `application : job_description = 1:N` 关系，同时仍然能为 overview 提供稳定的一行应用摘要。
- 当前手工收集 JD 和未来 scraper ingestion 都可以复用 `captured_at`，不需要改变 query contract。
- `application` 作为 current-state snapshot source，可以让 loader、query view 和未来 CLI/API/chatbot 消费者共享同一个状态边界。
- evidence email 字段让 overview 适合查询和 RAG 使用：结果既有当前状态，也能说明该状态来自哪封邮件。
- 避免在 `v_application_overview` 中重新实现 latest-status 计算，可以降低 view 和 loader 之间的语义漂移风险。

## Consequences

- 新 JD ingestion 必须尽量填充 `captured_at`；缺失时仍可通过 `jd_id DESC` 作为同级兜底排序。
- 如果 loader 同步 `application.latest_jd_id`，该同步逻辑也应使用 `captured_at DESC NULLS LAST, jd_id DESC`。
- `latest_status_email_id` 仍然是逻辑指针；需要通过 `v_inconsistent_status_snapshot` 检查它是否存在、是否仍属于同一个 application，以及是否和 snapshot 字段一致。
- `v_application_overview` 的字段命名应避免暗示实时推导：状态字段来自 `application` snapshot，evidence 字段来自被 snapshot pointer 指向的 email，JD 字段来自代表 JD snapshot。
- 查询层消费者应把 `v_application_overview` 理解为当前状态摘要，而不是完整历史；需要历史推进过程时应查询 `v_application_timeline`。
- 如果未来要加强 referential integrity，可以单独评估约束、触发器或 review table，而不是把该复杂度塞进 overview view。
