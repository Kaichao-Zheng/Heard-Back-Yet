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
```

Start the Docker PostgreSQL service defined in [`compose.yaml`](./compose.yaml):

```bash
docker compose up -d postgres
```

### Run Workflows

Run commands from the repository root in this order.

1. Add source files

- Application-related emails (`.eml`) → `data/eml/`
- Semi-structured job descriptions (`.md`) → `data/jd/`

2. Process source files

```bash
python -m scripts.run_data_pipeline
```

3. Normalize entity aliases manually

Follow [`scripts/normalize_aliases.md`](./scripts/normalize_aliases.md).

4. Rebuild PostgreSQL data and semantic search embeddings

```bash
python -m scripts.manage_db rebuild
```

5. Query application information

```powershell
python -m scripts.query_applications overview --limit 3
python -m scripts.search_chunks "Which roles sent assessments?" `
  --source-type email --email-type assessment --hydrate
```
