# 0006 Data and Scripts Layout

## Status

Accepted

## Context

- 旧目录 `data/raw/eml/source` 对复现者不直观，导入一封新 `.eml` 需要创建较深路径。
- 项目当前阶段只处理本地未脱敏数据，不维护 sanitized 复现数据出口。
- `scripts/` 已经同时包含入口脚本、ETL 实现、数据库实现和共享业务常量，需要分层。

## Decision

- `data/` 作为本地未脱敏数据工作区。
- 新 `.eml` 直接放在 `data/eml/`。
- 稳定命名后的 `.eml` 副本放在 `data/eml/renamed/`。
- 邮件 parsed JSON 放在 `data/eml/parsed/`。
- JD 原文放在 `data/jd/`，JD parsed JSON 放在 `data/jd/parsed/`。
- alias CSV 放在 `data/entity_aliases/`，并在 `scripts/normalize_aliases.md` checkpoint 人工复核 `normalized`。
- `scripts/` 根目录只放可直接运行的入口和人工 checkpoint。
- `scripts/etl/` 放 ETL 实现，`scripts/db/` 放 PostgreSQL 实现，`scripts/constants.py` 放业务标签和常量。
- `scripts/paths.py` 集中维护脚本使用的数据路径。

## Reasons

- 复现者可以把邮件直接放入 `data/eml/`，不需要理解 `raw/source` 这类内部历史语义。
- 现阶段所有 `data/` 内容均视为本地私有数据，不进入 Git。
- 入口脚本与实现脚本分离后，`scripts/` 根目录仍然易读，同时避免所有模块继续摊平。
- `constants.py` 属于招聘邮件和申请状态的业务语义，两侧 ETL 与 DB 都会引用；当前只有单个文件，因此保留在 `scripts/` 根目录，避免为了单文件创建目录。

## Consequences

- 历史日志中的旧路径不再代表当前实现。
- 旧 generated JSON 中的 `source_path` 如需完全同步新路径，需要单独迁移或重新跑完整 pipeline。
- `.gitignore` 需要忽略 `data/**`。
