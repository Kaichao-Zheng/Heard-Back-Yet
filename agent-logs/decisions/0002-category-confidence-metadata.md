# 0002 category confidence 元数据

## Status

Accepted

## Context

- V0 分类由本地 Ollama 模型 `qwen3.5:9b` 根据解析后的 JSON 执行。
- `category.label` 使用封闭枚举，便于后续 CSV / JSON / 数据库跟踪状态。
- `category.confidence` 来自模型输出，不是基于标注集校准过的统计概率。
- 如果只保存 `label` 和 `confidence`，后续很难判断模型来源、证据层级和是否需要人工复核。

## Decision

- `category.label` 有且仅有以下目标值之一：
  `applied`、`assessment`、`auth`、`delivery-failure`、`interview`、`logistics`、`offer`、`profile-update`、`rejection`、`unknown`、`unrelated`。
- `category.confidence` 定义为模型自评确信度，范围为 0 到 1，不代表客观准确率或可审计概率。
- 新增分类元数据字段：
  - `source`: 分类来源和证据层级，当前格式为 `ollama:<model>:<evidence>`，例如 `ollama:qwen3.5:9b:subject_sender` 或 `ollama:qwen3.5:9b:body_excerpt`。
  - `review_required`: 低置信度或 `unknown` 时标记为需要人工复核。

## Consequences

- 后续 UI 或人工复核流程不应把 `confidence` 当成真实概率展示。
- `review_required` 可以作为人工复核队列的第一层筛选条件。
- 如果未来引入标注集校准或规则分类器，可以通过 `source` 区分不同分类来源和证据层级。
