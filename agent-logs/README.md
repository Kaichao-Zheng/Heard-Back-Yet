# Agent Logs

This directory stores lightweight working records for agents and humans.
The goal is recoverable project context, not a full transcript.

## Principles

- Keep entries short, structured, and human-readable.
- Do not copy raw email content into logs.
- Do not store private candidate, recruiter, or company contact details unless they are already sanitized.
- Prefer paths, decisions, assumptions, validation results, and next steps.
- Update logs only when there is durable context worth preserving.

## Directory Roles

### `handoffs/`

Current state summaries for the next agent or human.

Use this for:

- What changed most recently.
- What is currently true.
- What should be read next.
- Immediate next steps.
- Known blockers or risks.

`handoffs/latest.md` should be the fastest recovery entrypoint.

### `progress/`

Chronological progress notes.

Use this for:

- Completed work sessions.
- Files changed.
- Commands or checks that matter.
- Test or validation results.

Each file should describe one coherent work session.

### `decisions/`

Durable design decisions.

Use this for:

- Directory layout choices.
- Data schema choices.
- Privacy and retention rules.
- Workflow conventions.

Each file should contain one decision and its reasoning.

## Suggested File Names

- `handoffs/latest.md`
- `handoffs/YYYY-MM-DD-short-topic.md`
- `progress/YYYY-MM-DD-short-topic.md`
- `decisions/0001-short-decision-title.md`

Use lowercase words separated by hyphens.

## Entry Templates

### Handoff

```md
# Handoff: YYYY-MM-DD Short Topic

## Current State

- ...

## Read First

- `AGENTS.md`
- `agent-logs/handoffs/latest.md`
- `docs/...`

## Next Steps

1. ...

## Known Issues

- ...
```

### Progress

```md
# Progress: YYYY-MM-DD Short Topic

## Summary

- ...

## Changed Files

- `path/to/file`

## Validation

- ...

## Follow-Up

- ...
```

### Decision

```md
# 0001 Short Decision Title

## Status

Accepted

## Context

- ...

## Decision

- ...

## Consequences

- ...
```

## Maintenance Rule

After a meaningful project change, update at least one of:

- `handoffs/latest.md` for current recovery context.
- `progress/YYYY-MM-DD-short-topic.md` for completed work.
- `decisions/NNNN-short-title.md` for durable design decisions.

Small typo fixes or formatting-only changes do not need a new log entry.
