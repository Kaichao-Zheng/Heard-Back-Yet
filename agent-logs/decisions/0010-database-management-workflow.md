# 0010 Database Management Workflow

## Status

Accepted

## Context

- PostgreSQL 本地生命周期原先由 `reset_db.py`、`load_postgres.py` 和 `index_chunks.py` 三个入口分别管理。
- 完整重建需要固定执行 reset → load → index，同时 indexing 仍需支持独立 preview、dry-run 和重建。
- Reset 是 destructive 操作；完整重建必须在删除数据库前检查 SQL、加载输入、Ollama 和 embedding model，避免在 index 阶段才发现外部依赖不可用。

## Decision

- 使用单一 `scripts/manage_db.py` CLI，提供 `reset`、`load`、`index`、`rebuild` 四个子命令。
- `rebuild_database()` 直接位于 `scripts/manage_db.py`，严格执行 preflight → reset → load → index；当前 prototype 不增加额外 workflow module。
- Reset、load 和 index 的实现继续位于独立应用模块；统一入口不把三种事务边界揉进同一实现函数。
- 原 `index_chunks.py` 文件名保留在 `heardbackyet/retrieval/index_chunks.py`，不再保留第二个同名 CLI 文件。
- `rebuild` preflight 检查 PostgreSQL 配置、schema/view SQL、parsed source/alias 输入以及 Ollama embedding model。

## Reasons

- 单一 CLI 降低本地操作记忆成本，独立子命令仍允许只刷新事实数据或 retrieval index。
- 明确的 `rebuild` 名称比扩张 `reset` 语义更安全，调用方能预期完整重建会执行三阶段写操作。
- External embedding 在 reset 前完成可用性检查，降低 destructive 操作后留下半完成数据库的风险。

## Consequences

- 旧 `scripts/reset_db.py`、`scripts/load_postgres.py` 和 `scripts/index_chunks.py` 入口由 `python -m scripts.manage_db <command>` 替代。
- `load --dry-run` 与 `index --preview/--dry-run` 保留；`rebuild` 始终执行完整正式流程。
- Reset、load 和 index 仍使用各自事务与连接生命周期；后续阶段失败时会明确报告失败阶段，但不会尝试自动恢复已经完成的 destructive reset。
