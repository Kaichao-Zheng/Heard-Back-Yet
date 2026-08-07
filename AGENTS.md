# AGENTS.md

## Project Goal

Build an email-driven workflow that transforms semi-structured recruiment `.eml` files into structured and trackable job application states.

The project focuses on email parsing, classification, and state tracking, while reserving extensibility for future querying and AI-assisted interaction.

## Stack

* Python
* PostgreSQL / pgvector
* SQLAlchemy
* FastAPI / Uvicorn
* CSV / JSON
* Git

## Rules

* Keep raw `.eml` files unchanged
* Use modular scripts
* Add comments for non-trivial logic
* Avoid hardcoded absolute paths
* Default to the smallest change necessary to complete the task
* Do not run `git add`, `git commit`, `git push` unless the user explicitly requests it

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
* `/heardbackyet/retrieval` for structured and content retrieval, indexing, and source hydration
* `/heardbackyet/conversation` for framework-neutral temporary-session coordination, query rewriting, and conversation stores
* `/heardbackyet/response` for the framework-neutral query-to-response workflow and response generation
* `/heardbackyet/presentation` for FastAPI app lifespan, routes, and public schemas
* `/heardbackyet/presentation/web` for FastAPI app lifespan, routes, public schemas, and static UI
* `/heardbackyet/presentation/weixin` for the Weixin/iLink channel adapter
* `/scripts` for thin runnable entrypoints and manual workflow checkpoints
* `/scripts/eval` for evaluation scripts and offline quality checks
* `/scripts/diag` for diagnostics and debugging helpers
* `/docs` for architecture notes

## Current Stage

Stage 7: Presentation Layer

The FastAPI/H5 path and bounded conversation context are in place.

The current focus is Weixin Access through a lightweight ClawBot/iLink Bridge that reuses the existing Conversation Layer and Canonical Response path.

## Stage History

* Stage 6: Evidence-grounded response generation with provenance-preserving answers
* Stage 5: Natural-language query orchestration, deterministic retrieval
  planning, structured/RRF execution, and CLI entry point
* Stage 4: Read-only query views/functions and pgvector semantic retrieval
* Stage 3: PostgreSQL schema, loader, derived `latest_status`, and validation SQL
* Stage 2: EML/JD evidence model and application grouping
* Stage 1: classification, entity extraction, and alias normalization
* Stage 0: validate the `.eml -> parsing -> structured output` pipeline
