# 0013 公共查询与 Scope 边界

## Context

- 数据库以 application（company + position）保存细粒度事实，但用户通常只能可靠表达 company。
- Position alias 面向 ETL 原文，无法覆盖用户的自由表述；application_id作为company+position定义的内部主键也不应成为用户输入。
- 当前公共 intent 混入诊断查询，company-only content search 又错误要求唯一 application。
- Classifier 的 outcome、intent、strict JSON 与错误处理 contract 由 Decision 0012 定义。

## Decision

- 公共 intent 仅保留 `application_overview`、`application_timeline`、`application_provenance`、`content_search`用于结构化查询与语义检索；两类 review query 只保留为开发者/管理的SQL/CLI操作。
- 简短、上下文无关且不依赖数据库或当前联网信息的稳定概念解释进入 `direct_answer`；它不是 retrieval intent，也不生成 `QuerySpec`。
- Compound query 进入 `requires_decomposition`，MVP 要求用户拆分，不实现自动分解。
- 采用 company-first scope：明确 company 即为合法 broad scope，不因同公司存在多个 application 自动判为歧义。
- Position 默认作为结果分组和 provenance，不作为 MVP hard filter；Classifier 不输出 position constraint，content search 仅通过原始问题保留岗位文字。
- Classifier 不接受 `application_id`、`company_id`、`position_id`、`position_hint` 或 `linked_only` 等内部或不可执行约束。
- Timeline 只接受 progress email labels；content search 接受 semantic-index labels（progress + supplementary info）；application provenance 最多接受一个 source type。
- Classifier 只提取用户可表达的约束；Planner 为 company-scoped content search 编排确定性的 company SQL resolution step，并把唯一 `company_id` 绑定到 semantic filter。

## Assumptions

- 用户查询粒度往往只能精确到company，会粗于数据库的company+position粒度，但结果必须保留 application/position 归属和证据来源。
- `company_singleton` 继续作为安全的 email-application fallback；未关联 email 可仅携带可验证的 company metadata。
- Salary/location 当前只作为原始内容参与 `content_search`，不提供结构化过滤。
- MVP 用户以中文提问，并正确拼写明确给出的公司名称；系统不承诺拼写纠错、语言翻译或英文查询兼容，合法简称由既有 alias normalization 处理。

## Limitations

- 暂不支持 multi-intent 执行、跨结果聚合、自动追问和 retrieval 结果的自然语言答案合成。
- 暂不保证任意 position 文本能映射到 canonical position。
- 暂不提供 semantic date filter 或跨轮上下文。
- `direct_answer` 暂不覆盖实时信息、联网查证、个性化建议或需要用户/application 上下文的问题。
- 暂不引入 LangChain/LangGraph；当前提交只完成 IntentClassifier contract。

## Consequences

- Decision 0011 的 company-scoped hybrid plan 已按 company-first 粒度绑定 `company_id`，不要求唯一 `application_id`。
