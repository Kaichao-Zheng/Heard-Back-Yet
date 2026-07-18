# 0009 Python Package Layout

## Status

Accepted

## Context

- Decision 0006 建立的 `scripts/etl`、`scripts/db` 分层适合早期脚本原型，但项目已新增 structured query、pgvector retrieval 和多个未来消费者。
- `scripts/query_applications.py` 与 `scripts/index_chunks.py` 同时承担 CLI 适配和可复用实现，部分入口、评估及诊断脚本需要注入 `sys.path` 才能导入模块。
- Query router 将同时依赖 structured query 与 semantic retrieval；在 router 实现前需要先稳定 Python import 和应用边界。

## Decision

- 正式应用包命名为 `heardbackyet`，直接放在仓库根目录；当前 prototype 不使用 `src` layout 或 editable install。
- 可复用的 constants、paths、ETL、DB、structured query 和 retrieval 实现放入 `heardbackyet/`。
- `scripts/` 保留 CLI、evaluation、diagnostic 和人工 checkpoint；CLI 只负责参数、连接生命周期、输出与错误码等适配工作。
- 包内和入口统一使用 `heardbackyet.*` 绝对导入，不再修改 `sys.path`；入口从仓库根以 `python -m scripts.<module>` 运行。
- `query_applications.py` 的 SQL view 查询函数迁入 `heardbackyet.query.view_queries`；retrieval indexing 函数迁入 `heardbackyet.retrieval.index_chunks`，保留原文件名。
- 本次不预建 routing framework；`heardbackyet.routing` 在实际 query-router contract 确定时加入。

## Reasons

- 产品名包比通用 `app` 更清楚，也能让 CLI、未来 FastAPI 和 chatbot 共享同一实现。
- 仓库根 package 在不引入安装步骤的前提下避免 router 建立在 CLI 模块之上，更符合当前 prototype 的直接运行体验。
- 迁移只建立 package 边界，不引入 repository、service interface、依赖注入或插件框架。

## Consequences

- 依赖继续由 `requirements.txt` 安装；项目本身不需要安装到虚拟环境。
- 历史日志中的 `scripts/etl`、`scripts/db` 和 `scripts/retrieval` 路径只代表当时实现；当前路径以 `heardbackyet/` 为准。
- `scripts/run_data_pipeline.py` 改为调用 `python -m heardbackyet.etl.<module>`，并从仓库根目录运行子步骤。
- Decision 0006 的 data layout 与 `scripts/` 入口原则继续有效，其 Python 实现目录部分由本决策替代。
