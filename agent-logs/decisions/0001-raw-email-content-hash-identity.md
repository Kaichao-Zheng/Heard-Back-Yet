# 0001 Message-ID Hash Email ID

## Status

Accepted

## Context

- V0 阶段需要把半结构化 `.eml` 转成可追踪的结构化状态。
- 邮件 `Date` 时间戳适合排序和索引，但现实中可能重复。
- 未来 RDB 会作为原始数据核心，主键不应依赖可能重复的 timestamp。
- 顺序号后缀如 `_01` 或 ` (1)` 依赖导入顺序，补导入历史邮件时不稳定。
- 成品 `.eml` 总量预计约 200 到 300 封，文件名中的短哈希主要服务人工阅读和辅助识别。
- MVP 样本中的邮件都具备 `Message-ID`，并且该字段原则上承担全球唯一邮件标识职责。
- 使用完整 `.eml` 原始 bytes 计算身份哈希存在设计冗余。
- 同一封邮件从不同客户端或不同时间导出时，外层 MIME、换行、导出元数据等 bytes 可能变化，导致内容哈希不稳定。
- MVP 不处理破损邮件或缺失 `Message-ID` 的邮件，遇到缺失字段应直接暴露错误。
- 项目需要一个稳定、短于原始 `Message-ID`、适合跨 CSV / JSON / 未来数据库引用的邮件实体 ID。

## Decision

- 项目的邮件实体 ID 命名为 `email_id`，其值为规范读取后的 `Message-ID` 文本计算出的完整 SHA-256。
- 原始 `Message-ID` 必须保留，用于追溯、核查和必要时回看邮件来源。
- 文件名中的短 SHA-256 仍保留，取 `email_id` 的前 8 位，而不是完整 `.eml` bytes 的哈希前缀。
- 输出文件名继续使用 `YYYYMMDD_HHMMSS_<hash-prefix> - 清洗后的原文件名.eml`。
- timestamp 保留为时间字段和可读排序前缀，不承担唯一主键职责。
- 重命名脚本不再使用 ` (1)`、` (2)` 这类 Windows 风格递增后缀来制造唯一文件名。

## Consequences

- 同一封邮件即使两次导出的 `.eml` bytes 不完全一致，只要 `Message-ID` 相同，就会得到相同 `email_id`。
- 缺失 `Message-ID` 的邮件在 MVP 中被视为输入不合格，不引入内容哈希兜底。
- 后续结构化输出或 RDB schema 应同时保存 `email_id` 和原始 `Message-ID`；`email_id` 作为项目内部邮件主键或唯一约束，`Message-ID` 作为追溯字段。
- 文件名中的 8 位短哈希不作为数据库主键，只作为 `email_id` 的可读短前缀。
