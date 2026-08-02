# Heard-Back-Yet

English | [中文](./README_ZH.md)

## 🚀Getting Started

This guide assumes you are using a Windows device.

```bash
git clone https://github.com/Kaichao-Zheng/Heard-Back-Yet.git
```

### Activate the Virtual Environment

```bash
# create environment
python -m venv .venv         # or other name you like

# activate environment
source .venv/bin/activate    # macOS/Linux
.\.venv\Scripts\activate     # Windows Powershell
```

### Install Dependencies

```bash
pip install -r requirements.txt
python -m pip freeze > requirements.txt
```

### Configure Environment Variables

Copy the file `.env.example` and rename the file to `.env` in the root directory.

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=heardbackyet
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

MODEL_PROVIDER=ollama
# MODEL_PROVIDER=alibaba_model_studio

OLLAMA_URL=http://localhost:11434
MODEL_BASE_URL=https://your-openai-compatible-endpoint.example/v1
MODEL_API_KEY=

TEXT_CLASSIFICATION_MODEL=qwen3.6:27b
ENTITY_EXTRACTION_MODEL=qwen3.5:9b
EMBEDDING_MODEL=qwen3-embedding:4b
INTENT_CLASSIFICATION_MODEL=qwen3.6:27b
RESPONSE_GENERATION_MODEL=qwen3.6:27b
```

> [!NOTE]
>
> Local inference could hit VRAM limits when different models are loaded in sequence. A hosted provider avoids local model switching, but sends model inputs to an external service. Changing the Embedding provider or model requires an explicit index rebuild before semantic or hybrid retrieval can use the new vector space.
>
> `MODEL_PROVIDER=alibaba_model_studio` uses the service's OpenAI-compatible
> endpoints and provider-specific extensions such as `enable_thinking`.

### Run a Model API Smoke Test

This checks every unique module which configured a model.

```powershell
python -m scripts.diag.smoke_model_api
```

The complete smoke test can be slow with local Ollama because it loads multiple
models sequentially.

### Start PostgreSQL

Start the Docker PostgreSQL service defined in [`compose.yaml`](./compose.yaml):

```bash
docker compose up -d postgres
```

`PostgreSQL` can run locally, but `pgvector` is cumbersome to build on Windows. Docker avoids that setup.

### Run Workflows

Run commands from the repository root in this order.

#### 1. Add source files

- Application-related emails (`.eml`) → `data/eml/`
- Semi-structured job descriptions (`.md`) → `data/jd/`

#### 2. Process source files

```bash
python -m scripts.run_data_pipeline
```

#### 3. Normalize entity aliases manually

Follow [`scripts/normalize_aliases.md`](./scripts/normalize_aliases.md).

#### 4. Rebuild PostgreSQL data and semantic search embeddings

```bash
python -m scripts.manage_db rebuild
```

#### 5. Query job applications

Run the same query through either interface.

**Option A — Diagnostic CLI**

Run the query pipeline directly.

```powershell
python -m scripts.run_query "哪些岗位要求AWS"
```

**Option B — HTTP API**

Run the Uvicorn development server listening on port `8000`:

```powershell
python -m uvicorn heardbackyet.presentation.app:app --reload
```

Send a user query to the versioned API in another terminal:

```powershell
curl.exe --json '{\"user_query\":\"哪些岗位要求AWS\"}' http://127.0.0.1:8000/api/v1/responses
```

Press `Ctrl+C` in the **server terminal** to stop Uvicorn.

> [!NOTE]
>
> `哪些岗位要求AWS` (`Which roles require AWS`) is a deliberatly vague regression query:
>
> - It avoids cross-lingual noise from the primarily Chinese corpus.
> - It can expose UTF-8 handling issue throughout the workflow.
> - It creates a borderline choice between `missing_scope` and a summarized `content_search`.
> - It includes the exact lexical term AWS, helping validate the hybrid retrieval optimization.
>   - For this query, the semantic retriever ranks email evidence above JD.

**Bonus. Inspect diagnostic checkpoints**

See how user queries are orchestrated in [`docs/query_orchestration_sequence.md`](docs/query_orchestration_sequence.md).

```powershell
# Smoke response-model access
python -m scripts.run_query "哪些岗位要求AWS" --llm-only

# Inspect retrieved evidence
python -m scripts.run_query "哪些岗位要求AWS" --evidence

# Inspect the intent-classifier handoff
python -m scripts.run_query "哪些岗位要求AWS" --query-spec
```

**Bonus. Try the lower-level retrieval tools**

```powershell
# Structured retrieval
python -m scripts.query_applications overview --limit 3

# Semantic retrieval
python -m scripts.search_chunks "Which roles sent assessments" `
  --mode semantic `
  --source-type email `
  --email-type assessment `
  --hydrate

# Lexical retrieval
python -m scripts.search_chunks "AWS" `
  --mode lexical `
  --source-type job_description `
  --hydrate

# Hybrid retrieval (semantic & lexical RRF)
python -m scripts.search_chunks "Which roles require AWS" `
  --mode hybrid `
  --source-type job_description `
  --semantic-weight 1.0 `
  --lexical-weight 1.0 `
  --hydrate
```

## 📊Evaluation

Run the commands from the repository root after
[activating the virtual environment](#create-a-virtual-environment).

### 1. Evaluate saved email classification results

- Expected columns require manual annotation.

```powershell
python -m scripts.eval.evaluate_email_classifier
```

**Overwrites:**

- [`data/eval/label_comparison.csv`](./data/eval/label_comparison.csv)
- [`data/eval/label_metrics.csv`](./data/eval/label_metrics.csv)

### 2. Evaluate saved email entity extraction results

- Expected columns require manual annotation.

```powershell
python -m scripts.eval.evaluate_email_entity_extractor
```

**Overwrites:**

- [`data/eval/company_comparison.csv`](./data/eval/company_comparison.csv)
- [`data/eval/company_metrics.csv`](./data/eval/company_metrics.csv)
- [`data/eval/position_comparison.csv`](./data/eval/position_comparison.csv)
- [`data/eval/position_metrics.csv`](./data/eval/position_metrics.csv)

### 3. Visualize the embedding-space PCA

- Requires indexed PostgreSQL retrieval chunks and the configured embedding model.

```powershell
python -m scripts.eval.visualize_embeddings
```

**Overwrites:**

- [`data/eval/embedding_space_pca.png`](./data/eval/embedding_space_pca.png)

### 4. Evaluate query intent classification

Score saved predictions:

```powershell
python -m scripts.eval.evaluate_query_intent_classifier
```

Regenerate predictions:

- Expected columns require manual annotation.
- This command calls the configured LLM.

```powershell
python -m scripts.eval.evaluate_query_intent_classifier --force
```

**Overwrites:**

- [`data/eval/intent_comparison.csv`](./data/eval/intent_comparison.csv)
- [`data/eval/intent_metrics.csv`](./data/eval/intent_metrics.csv)
