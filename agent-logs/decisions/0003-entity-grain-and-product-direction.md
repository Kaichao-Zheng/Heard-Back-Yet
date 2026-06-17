# 0003 Entity Grain and Product Direction

## Status

Proposed

## Context

- 项目最初是求职邮件标注 smoking test，目标是验证 `.eml -> parsing -> structured output -> label` 是否可行。
- smoking test 已基本完成，后续价值点正在转向 NER、人工维护 Markdown JD，以及 labelled data 上的 RAG。
- 当前 JSON 已预留 `company` 和 `position` 结构，但字段语义还没有完全固化。
- 用户可能对同一 company 投递多个 position，也可能在春招/秋招重复投递同一 company + position。

## Proposed Direction

- 优先抽取 `company` 和 `position` 两类求职核心实体。
- `candidates` 保留邮件中识别出的原始候选，数量不限，但需要满足候选阈值。
- `raw` 保留邮件原文或模型看到的候选表述。
- `normalized` 暂按 alias mapping 后的归一化别名理解；LLM 可以辅助维护 alias mapping，但最终 canonical company / position 由人工确认。
- job seeking state 暂按 position 粒度管理，而不是 company 粒度。
- dashboard 中重复 company 是合法的，因为多个 position 的状态和时间线应相互独立。
- `category.label` 是状态来源之一，但不是所有 label 都应转成 job state。

## Open Trade-offs

- 更严格的实体粒度应是 application，但 V0/V0.5 可能暂不引入完整 `application_id`。
- 对同一 company + position 的春招/秋招重复投递，当前可以暂时接受后一次 `applied` 覆盖旧 `interviewed` / `offered` 状态，但这不是最终设计。
- `interview` 二级细分对 demo 阶段收益有限，暂不应优先拆分。

## Consequences

- 后续 schema 设计需要避免把 company 当作唯一状态主体。
- NER 输出与人工确认实体需要分层，避免把模型候选误当作真实投递事实。
- RAG 应结合邮件标签、实体候选、alias mapping、人工 JD，而不是只检索邮件正文。
