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

To reduce context loss across sessions, update `agent-logs` in Chinese after every meaningful project change.

After changing code, scripts, docs, data schemas, or workflow decisions, update at least one of:

* `agent-logs/handoffs/latest.md` for current recovery context
* `agent-logs/progress/YYYY-MM-DD-short-topic.md` for completed work
* `agent-logs/decisions/NNNN-short-title.md` for durable decisions

## Folder Structure

* `/data/raw/eml` for source emails
* `/data/raw/jd` for source job descriptions
* `/scripts` for parsing scripts
* `/docs` for architecture notes

## Current Stage

V0:
`.eml -> parsing -> structured output`
