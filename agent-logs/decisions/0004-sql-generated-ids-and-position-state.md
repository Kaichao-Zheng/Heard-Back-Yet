# 0004 Application Tracking Schema 与 SQL Generated IDs

## Status

Accepted

## Context

- EML parsed JSON 和 JD parsed JSON 是前置衍生记录，目标是保留原始证据、业务字段和追溯字段，不负责提供数据库主键。
- SQL 导入层可以生成 `email_id`、`jd_id`、`company_id`、`position_id`、`application_id`、alias table ID 等 surrogate key。
- `Message-ID` 和 `message_id_hash` 适合用于邮件身份、去重、文件命名和追溯，但不适合作为业务聚合维度。
- `docs/conceptual_schema.md` 中的 schema 已经将 canonical entity、alias mapping、best-effort application grouping 和 source evidence records 分层。
- 输入数据本身有噪声：公司名和岗位名可能不一致，AI 抽取结果可能不可靠，部分邮件或 JD 在导入时无法确定归属到哪个 application。

## Decision

- 数据库主键由 SQL 层或导入脚本生成。parsed EML/JD JSON 保留 `message_id`、`message_id_hash`、项目相对 `source_path` 等来源字段，但不提供 SQL ID。
- 使用 canonical entity tables 保存归一化实体：
  - `COMPANY(company_id, company_name)`
  - `POSITION(position_id, position_name)`
- 使用 alias mapping tables 保存可复用的归一化规则：
  - `COMPANY_ALIAS(raw_name, company_id)`
  - `POSITION_ALIAS(raw_name, position_id)`
- 在 evidence records 上保留原始抽取值：
  - `EMAIL.company_raw`
  - `EMAIL.position_raw`
  - `JOB_DESCRIPTION.company_raw`
  - `JOB_DESCRIPTION.position_raw`
- 引入 `APPLICATION.application_id` 作为 application tracking unit，用来表达一个 best-effort 的 company-position application cluster。
- 目前不对 `APPLICATION(company_id, position_id)` 加唯一约束。同一个 company-position pair 现实中可能出现一岗多投、重新投递、春招/秋招批次、渠道差异或归组不确定，因此可能出现多条 application records。
- 这里的 trade-off 是：schema 给 application attempt 留出表达空间，但不声称系统能够精确识别每一次真实投递。即便人工 review，很多时候也只能依据邮件时间线、JD 时间、批次描述等线索做 best guess，准确率仍然有限。
- evidence records 通过可为空的外键关联 application：
  - `EMAIL.application_id nullable`
  - `JOB_DESCRIPTION.application_id nullable`
- 分类结果概念命名为 `email_type`，不使用 `event_type`。因为 `auth`、`profile-update`、`unknown` 等标签是邮件类别，不一定是 application status event。
- `APPLICATION.latest_status` 是由 status-driving emails 推导出来的 snapshot/cache，不是 source of truth。

## Reasons

- 单独的 `application_id` 可以给后续表和功能提供稳定引用，避免在所有 child tables 中重复使用 `(company_id, position_id)` 作为 composite foreign key。
- raw fields 和 canonical entities 分离，可以保留追溯能力，也方便审计 AI 抽取错误。
- alias tables 表示已知的归一化规则；`*_raw` 字段表示某一条 source record 或 AI extraction 实际产生了什么文本。
- nullable evidence links 允许系统先导入数据，再做人工 review 或后续自动 matching。OTP/auth 邮件、unknown 邮件、generic assessment 邮件和模糊 JD 都需要这种空间。
- 不给 `(company_id, position_id)` 加唯一约束，是为了避免 schema 假装一个公司-岗位组合永远只对应一次真实投递。
- 同时，允许多条 application records 也不是在保证可以可靠拆分每一次投递；它只是让后续人工 review 或 matching logic 可以记录当前最合理的 grouping guess，并保留不确定性。
- `latest_status` 便于查询和 UI 展示，但原始状态证据仍然来自已关联的 `EMAIL.email_type` 以及邮件时间线。

## Consequences

- 旧的 V0 结论“只做 position-level state view，暂不引入 `application_id`”已被新的 `APPLICATION` grouping table 取代。
- SQL import 或后续 normalization 逻辑需要负责创建或解析 canonical company/position、alias mappings 和 application records。
- `message_id_hash` 仍可用于邮件去重、追溯和稳定文件命名，但不能用于 application state aggregation。
- 部分 source records 会有意保持 `application_id = null`，直到 review 或更可靠的 matching logic 可以处理它们。
- application grouping 的结果应被理解为可修正的 best-effort tracking cluster，而不是确定的真实世界投递实例。
- status calculation 应忽略非状态驱动的 `email_type`，例如 `auth`、`profile-update`、`unknown`，除非后续规则明确改变。
- 如果未来一封邮件需要关联多个 applications，应新增类似 `APPLICATION_EMAIL` 的 junction table，而不是继续扩展单一 `EMAIL.application_id`。
