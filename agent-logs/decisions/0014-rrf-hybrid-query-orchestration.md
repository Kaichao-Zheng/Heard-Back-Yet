# 0014 RRF Hybrid Query Orchestration

## Status

Accepted

## Context

- Retriever 层已经提供 semantic、BM25 lexical 与 RRF fusion，但 orchestration 的 content step 仍固定调用 dense-only `search_semantic()`。
- Decision 0011 中的 `RetrievalMode.HYBRID` 表示“structured company resolution + semantic search”，与 retriever 层 conventional hybrid ranking 的含义冲突。
- Classifier 只负责输出用户 intent 与可执行约束，不应让模型选择 retrieval backend 或 RRF 权重。

## Decision

- Planner 现有 `RetrievalPlan.mode` 与 `_plan_semantic()` / `_plan_hybrid()` 拓扑保持不变：旧 `HYBRID` 仍表示 structured company resolution 后接 semantic step。
- `SemanticRetrievalStep` 继续表示 orchestration 层的语义内容检索需求，并新增独立的下层 `RetrievalBackend`；Planner 生成的 semantic step 默认选择 semantic + lexical 的 RRF hybrid backend。
- Classifier 与 `QuerySpec` 不新增 matching mode 或 backend 字段；普通用户问题和 LLM 输出不控制 ranking implementation。
- Planner 使用内部配置选择 content retrieval backend；默认值为 hybrid，测试与诊断调用方仍可显式覆盖为 semantic 或 lexical。
- Executor 根据 step 的 `backend` 委托 `search_semantic()`、`search_lexical()` 或 `search_hybrid()`，不在 orchestration 层复制 BM25、embedding 或 RRF 逻辑。
- 已有显式 semantic step 的默认行为不变；Planner 的公共 content-search route 使用 RRF hybrid。
- `QuerySpec` 不增加 backend、RRF K 或权重字段。相关调参仍属于 retriever/评估边界，不能由普通用户问题或 LLM 输出控制。

## Reasons

- Scope resolution topology 与 ranking backend 是正交职责：前者决定候选集合，后者决定同一过滤集合内的排序。
- `RetrievalMode` 只描述 plan topology，`RetrievalBackend` 只描述 semantic step 的 ranking implementation，避免同一个 `HYBRID` 枚举值承担两层含义。
- Semantic step 明确记录下层 backend，Executor 明确分派实现，才能让 `Classifier -> Planner -> Executor -> Retrieval` 的行为可审计。
- 默认 backend 与唯一 backend 必须区分，但当前 prototype 没有真实使用频率或质量数据支撑逐 query 自适应路由，因此不扩张 Classifier 契约。
- 保留 semantic backend 与旧 step import，减少对诊断代码和已有内部调用方的破坏。

## Consequences

- 无 company 的 content search 保持 semantic plan topology，但 semantic step 改为执行 RRF hybrid，不再默认 dense-only。
- 有 company 的 content search 先确定性解析唯一 `company_id`，再把同一 metadata filter 同时应用到 semantic 与 lexical 候选。
- Structured intent 的执行行为不变；直接调用 `scripts.search_chunks --mode semantic` 的诊断能力也不变。
- Pure lexical execution 不要求 embedder；semantic 与 hybrid execution 仍要求 embedder。
- 已知 AWS 样例只证明该集成能复现一个已观察到的改善，不代表整体检索质量已经提升；总体结论仍需人工 relevance labels 与 Hit@3、Recall@K、MRR 评估。

## Deferred Reranking

- 当前 MVP 的内容排序终止于 semantic + lexical weighted RRF，本阶段不增加独立 reranker、reranking step 或第二套模型 runtime。
- 该决定属于范围控制，不代表 RRF 已被证明优于 Cross-encoder 或 LLM reranking。当前原始邮件预计长期保持百级，已有观察表明有效内容基本能够进入 Top-5，但尚无 retrieval relevance set 或端到端 RAG evaluation 证明候选内部顺序会损害最终答案。

| 方案 | 问题 |
| --- | --- |
| 9B Ollama reranker | 可靠性未知 |
| 27B Ollama reranker | 当前 classifier 单 query 已约需 30 秒，额外 rerank 会继续叠加在线延迟 |
| 专用小 reranker | 增加第二套 runtime |

- 当前公开 `SearchRequest.limit` 默认值仍为 10；“RRF Top-10 -> rerank -> RAG Top-5”只是待验证方案，不是现有运行行为。
- 当人工 relevance evaluation 证明候选 Recall@10 足够，但 MRR、nDCG@5 或最终 RAG 答案质量持续因候选顺序受损，并且已经定义可接受的延迟与运行成本预算时，再重新评估 reranker。
- 后续若决定引入 reranker，应单独记录模型 runtime、candidate/context limit、失败 fallback、provenance 与 latency contract。
