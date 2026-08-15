| Layer | Responsibility | Components |
| --- | --- | --- |
| Presentation Layer<br>展示层 | Adapt user input and responses for web and Weixin channels<br>适配网页与微信渠道的用户输入和响应 | H5, Web API, Weixin Bridge<br>H5 前端、Web API、微信桥接器 |
| Conversation Layer<br>会话层 | Coordinate temporary conversation context and follow-up rewriting<br>协调短期对话上下文与追问改写 | Conversation Context, Follow-up Rewriter<br>对话上下文、追问改写 |
| Response Layer<br>响应层 | Assemble the canonical, evidence-grounded response<br>组装基于证据的统一响应 | Query-to-Response Workflow, Response Generator<br>查询-响应工作流、回答生成 |
| Orchestration Layer<br>编排层 | Recognize intent, plan retrieval, and execute retrieval steps<br>识别意图、规划检索并执行检索步骤 | Intent Classifier, Retrieval Planner, Retrieval Executor<br>意图分类、检索规划、检索执行 |
| Retrieval Layer<br>检索层 | Retrieve and hydrate structured or content evidence<br>检索并补全结构化或内容证据 | Structured/Semantic/Lexical/Hybrid Retrievers<br>结构化/语义/关键词/混合检索 |
| Database Layer<br>数据库层 | Serve relational business facts and vector indexes<br>为查询提供关系型业务事实和向量索引 | PostgreSQL, pgvector, SQLAlchemy |
