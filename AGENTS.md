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

* `/data/raw/eml` for stable-named source emails
* `/data/raw/eml/source` for newly imported `.eml` files before stable renaming
* `/data/raw/eml/parsed` for parsed email JSON intermediates
* `/data/raw/jd` for source job descriptions
* `/scripts` for parsing scripts
* `/docs` for architecture notes

## Current Stage

V0:
`.eml -> parsing -> structured output`
