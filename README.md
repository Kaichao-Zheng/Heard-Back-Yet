# Heard-Back-Yet

English | [中文](./README_ZH.md)

## 🚀Getting Started

This guide assumes you are using a Windows device.

```bash
git clone https://github.com/Kaichao-Zheng/Heard-Back-Yet.git
```

### Create a Virtual Environment

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

OLLAMA_URL=http://localhost:11434
TEXT_CLASSIFICATION_MODEL=qwen3.6:27b
ENTITY_EXTRACTION_MODEL=qwen3.5:9b
EMBEDDING_MODEL=qwen3-embedding:4b
INTENT_CLASSIFICATION_MODEL=qwen3.6:27b
```

Start the Docker PostgreSQL service defined in [`compose.yaml`](./compose.yaml):

```bash
docker compose up -d postgres
```

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

> [!NOTE]
>
> English query quality may vary because the corpus is primarily Chinese.

```powershell
python -m scripts.run_query "Which roles require AWS"
```

See how queries are orchestrated in [`docs/query_orchestration_sequence.md`](docs/query_orchestration_sequence.md).

#### Opt. Try the low-level query and retrieval tools

```powershell
# Structured query
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

## Evaluation

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
