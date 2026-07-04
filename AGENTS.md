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
* `/scripts` for runnable entrypoints and manual workflow checkpoints
* `/scripts/etl` for ETL implementation scripts
* `/scripts/db` for database configuration, models, and loader implementation
* `/scripts/eval` for evaluation scripts and offline quality checks
* `/scripts/diag` for diagnostics and debugging helpers
* `/scripts/constants.py` for domain labels and workflow constants
* `/docs` for architecture notes

## Current Stage

Stage 4: Query Layer
The project is adding read-only SQL views and Python query functions for common
application tracking questions, built on top of the V3 PostgreSQL foundation.
This layer should preserve evidence provenance and prepare stable query
contracts for future CLI, FastAPI, and chatbot consumers.

## Stage History

* Stage 3: PostgreSQL schema, loader, derived `latest_status`, and validation SQL
* Stage 2: EML/JD evidence model and application grouping
* Stage 1: classification, entity extraction, and alias normalization
* Stage 0: `.eml -> parsing -> structured output`
