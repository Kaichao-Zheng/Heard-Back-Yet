from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from heardbackyet.db.config import PostgresConfig, load_postgres_config
from heardbackyet.db.load_postgres import print_summary as print_load_summary
from heardbackyet.db.load_postgres import run_load
from heardbackyet.db.postgres_loader import LoadStats
from heardbackyet.db.reset_db import (
    INIT_SCHEMA_PATH,
    INIT_VIEWS_PATH,
    print_reset_context,
    read_sql_statements,
    reset_database,
)
from heardbackyet.paths import (
    COMPANY_ALIASES_PATH,
    EML_PARSED_DIR,
    JD_PARSED_DIR,
    POSITION_ALIASES_PATH,
)
from heardbackyet.retrieval.index_chunks import (
    IndexStats,
    RetrievalDocument,
    run as run_index,
)
from heardbackyet.retrieval.text_embedder import (
    EmbeddingConfig,
    load_embedding_config,
)


OLLAMA_PREFLIGHT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class RebuildResult:
    database: str
    load: LoadStats
    index: IndexStats


def rebuild_database(
    progress: Callable[[str], None] | None = None,
    on_load_complete: Callable[[LoadStats], None] | None = None,
) -> RebuildResult:
    """Validate dependencies, then reset, load, and index the local database."""
    emit = progress or (lambda _stage: None)

    emit("preflight")
    config = preflight_rebuild()

    emit("reset")
    print_reset_context(config)
    reset_database(config)
    print(f"Database {config.database!r} reset successfully.")

    emit("load")
    load_stats = run_load(dry_run=False)
    if on_load_complete is not None:
        on_load_complete(load_stats)

    emit("index")
    index_stats, _ = run_index(preview=False, dry_run=False)
    return RebuildResult(config.database, load_stats, index_stats)


def preflight_rebuild() -> PostgresConfig:
    """Fail before destructive reset when local inputs or Ollama are unavailable."""
    config = load_postgres_config()
    read_sql_statements(INIT_SCHEMA_PATH)
    read_sql_statements(INIT_VIEWS_PATH)

    for path in (
        EML_PARSED_DIR,
        JD_PARSED_DIR,
        COMPANY_ALIASES_PATH,
        POSITION_ALIASES_PATH,
    ):
        if not path.exists():
            raise RuntimeError(f"Required rebuild input does not exist: {path}")

    embedding_config = load_embedding_config()
    ensure_embedding_model_available(embedding_config)
    return config


def ensure_embedding_model_available(config: EmbeddingConfig) -> None:
    endpoint = config.endpoint + "/api/tags"
    request = Request(endpoint, method="GET")
    try:
        with urlopen(request, timeout=OLLAMA_PREFLIGHT_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(
            f"Ollama preflight failed with HTTP {exc.code}: {endpoint}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Cannot reach Ollama during rebuild preflight: {exc}") from exc

    raw_models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        raise RuntimeError("Ollama /api/tags returned an unexpected response.")

    available = {
        value
        for item in raw_models
        if isinstance(item, dict)
        for value in (item.get("name"), item.get("model"))
        if isinstance(value, str)
    }
    if config.model not in available and f"{config.model}:latest" not in available:
        raise RuntimeError(
            f"Embedding model {config.model!r} is not available in Ollama."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset, load, index, or fully rebuild the local PostgreSQL data store."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset = subparsers.add_parser(
        "reset", help="Recreate the database, schema, and views."
    )
    reset.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and SQL without changing PostgreSQL.",
    )

    load = subparsers.add_parser(
        "load", help="Load parsed sources and aliases into PostgreSQL."
    )
    load.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the loader and roll back its transaction.",
    )

    index = subparsers.add_parser(
        "index", help="Render sources and rebuild retrieval embeddings."
    )
    add_index_arguments(index)

    subparsers.add_parser(
        "rebuild",
        help="Preflight, reset, load, and index the complete local database.",
    )
    return parser.parse_args()


def add_index_arguments(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preview",
        action="store_true",
        help="Render and count chunks without calling Ollama or writing PostgreSQL.",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the index in one transaction, then roll it back.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        choices=("email", "jd"),
        default=None,
        help="Optionally restrict preview/dry-run to email or JD sources.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        help=(
            "Process at most this many rendered chunks. "
            "Only valid with --preview or --dry-run."
        ),
    )


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def print_index_summary(
    stats: IndexStats,
    preview: bool,
    dry_run: bool,
    details: bool = True,
    result_prefix: str = "",
) -> None:
    if details:
        print(f"eligible email sources: {stats.eligible_emails}")
        print(f"rendered email chunks: {stats.rendered_emails}")
        print(f"job description sources: {stats.job_descriptions}")
        print(f"rendered job description chunks: {stats.rendered_job_descriptions}")
    if preview:
        print(
            f"{result_prefix}Preview complete; "
            "Ollama and retrieval_chunk were not changed."
        )
    elif dry_run:
        print(
            f"{result_prefix}Dry run indexed {stats.indexed_chunks} chunks; "
            "transaction rolled back."
        )
    else:
        print(f"{result_prefix}Committed {stats.indexed_chunks} retrieval chunks.")


def print_preview_samples(
    documents: list[RetrievalDocument],
    limit: int | None,
) -> None:
    if limit is not None:
        samples = documents
    else:
        samples_by_source_type: dict[str, RetrievalDocument] = {}
        for document in documents:
            samples_by_source_type.setdefault(document.metadata.source_type, document)
        samples = list(samples_by_source_type.values())

    if not samples:
        print("No rendered chunk sample available.")
        return

    heading = "Rendered chunk(s):" if limit is not None else "Rendered chunk sample(s):"
    print(heading)
    print(json.dumps([asdict(sample) for sample in samples], ensure_ascii=False, indent=2))


def run_command(args: argparse.Namespace) -> None:
    if args.command == "reset":
        config = load_postgres_config()
        print_reset_context(config)
        if args.dry_run:
            print("Dry run complete; database was not changed.")
            return
        reset_database(config)
        print(f"Database {config.database!r} reset successfully.")
        return

    if args.command == "load":
        print_load_summary(run_load(args.dry_run), args.dry_run)
        return

    if args.command == "index":
        stats, candidates = run_index(
            args.preview, args.dry_run, args.limit, args.source
        )
        if args.preview:
            print_preview_samples(candidates, args.limit)
        print_index_summary(stats, args.preview, args.dry_run)
        return

    if args.command == "rebuild":
        result = rebuild_database(
            progress=lambda stage: print(f"== {stage} =="),
            on_load_complete=lambda stats: print_load_summary(stats, dry_run=False),
        )
        print_index_summary(
            result.index,
            preview=False,
            dry_run=False,
            details=False,
            result_prefix="- ",
        )
        print(f"Database {result.database!r} rebuilt successfully.")
        return

    raise ValueError(f"Unsupported command: {args.command}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    try:
        run_command(args)
    except Exception as exc:
        print(f"manage_db failed during {args.command}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
