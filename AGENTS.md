# AGENTS.md

## Project Goal

Build an email-driven workflow that transforms semi-structured recruiment `.eml` files into structured and trackable job application states.

The project focuses on email parsing, classification, and state tracking, while reserving extensibility for future querying and AI-assisted interaction.

## Stack

* Python
* CSV / JSON
* Git

## Rules

* Keep raw `.eml` files unchanged
* Use modular scripts
* Add comments for non-trivial logic
* Avoid hardcoded absolute paths

## Agent Logs

After every meaningful project change, update `agent-logs` in Chinese.
Use `agent-logs/README.md` for log types, naming, templates, and maintenance rules.

## Folder Structure

* `/data/eml` for newly imported `.eml` files before stable renaming
* `/data/eml/renamed` for stable-named source email copies
* `/data/eml/parsed` for parsed email JSON intermediates
* `/data/jd` for source job descriptions
* `/data/jd/parsed` for parsed JD JSON intermediates
* `/data/entity_aliases` for local alias CSV files before manual normalization
* `/data/eval` for evaluation CSV inputs and generated quality metrics
* `/heardbackyet` for importable application and domain implementation
* `/heardbackyet/etl` for ETL implementation
* `/heardbackyet/db` for database configuration, models, and loader implementation
* `/heardbackyet/query` for structured application query functions
* `/heardbackyet/retrieval` for semantic indexing, search, and hydration
* `/scripts` for thin runnable entrypoints and manual workflow checkpoints
* `/scripts/eval` for evaluation scripts and offline quality checks
* `/scripts/diag` for diagnostics and debugging helpers
* `/docs` for architecture notes

## Current Stage

Stage 6: Evidence-Grounded Response Generation

The project is turning `QueryOrchestrationResult` into concise user-facing
responses. Resolved queries must answer only from returned evidence and preserve
provenance; other outcomes must return an appropriate direct answer,
clarification request, decomposition notice, or unsupported notice.
`scripts.run_query` remains the first presentation surface. FastAPI, frontend,
multi-turn state, and repository-wide Ollama seeding are outside this stage.

## Stage History

* Stage 5: Natural-language query orchestration, deterministic retrieval
  planning, structured/RRF execution, and CLI entry point
* Stage 4: Read-only query views/functions and pgvector semantic retrieval
* Stage 3: PostgreSQL schema, loader, derived `latest_status`, and validation SQL
* Stage 2: EML/JD evidence model and application grouping
* Stage 1: classification, entity extraction, and alias normalization
* Stage 0: `.eml -> parsing -> structured output`
