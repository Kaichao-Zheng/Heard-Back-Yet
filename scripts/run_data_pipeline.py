from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from paths import ENV_PATH

load_dotenv(ENV_PATH)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_CHECK_TIMEOUT_SECONDS = 3


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def script_root() -> Path:
    return Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the source processing pipeline: EML rename/parse, email classify, "
            "email entity extract, job description parse, and alias append."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass --dry-run to each pipeline step.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full output from each pipeline step.",
    )
    parser.add_argument(
        "--force-classify",
        action="store_true",
        help="Reclassify files that already have category.label.",
    )
    parser.add_argument(
        "--force-extract",
        action="store_true",
        help="Re-extract files that already have selected entities.",
    )
    return parser.parse_args()


def step_command(script_name: str, *flags: str) -> list[str]:
    module_name = f"etl.{Path(script_name).stem}"
    return [sys.executable, "-m", module_name, *flags]


def summary_line(output: str) -> str:
    alias_lines = [
        line
        for line in output.splitlines()
        if line.startswith("company: ") or line.startswith("position: ")
    ]
    if alias_lines:
        return "\n".join(alias_lines)

    for line in reversed(output.splitlines()):
        if line.startswith("Processed: ") or (
            line.startswith("No ") and (" found" in line or " needed" in line)
        ):
            return line
    return "Completed"


def run_step(
    label: str, command: list[str], verbose: bool, requires_ollama: bool = False
) -> None:
    print(f"== {label} ==")
    if requires_ollama:
        ensure_ollama_available(label)

    if verbose:
        subprocess.run(command, cwd=script_root(), check=True)
        return

    result = subprocess.run(
        command,
        cwd=script_root(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        print(summary_line(result.stdout))
        return

    print("Failed:")
    print(f"  exit_code={result.returncode}")
    if result.stdout:
        print("Stdout:")
        print(result.stdout.rstrip())
    if result.stderr:
        print("Stderr:")
        print(result.stderr.rstrip())
    raise SystemExit(result.returncode)


def ensure_ollama_available(step_label: str) -> None:
    endpoint = OLLAMA_URL.rstrip("/") + "/api/tags"
    request = urllib.request.Request(endpoint, method="GET")

    try:
        with urllib.request.urlopen(
            request, timeout=OLLAMA_CHECK_TIMEOUT_SECONDS
        ) as response:
            response.read(1)
    except (OSError, urllib.error.URLError) as error:
        print("Ollama is not reachable.")
        print(f"  step={step_label}")
        print(f"  url={OLLAMA_URL}")
        print(f"  Start Ollama before running the {step_label} step.")
        print(f"  reason={error}")
        raise SystemExit(1) from error


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    dry_run_flag = ["--dry-run"] if args.dry_run else []

    run_step("rename_eml", step_command("rename_eml.py", *dry_run_flag), args.verbose)

    run_step("parse_eml", step_command("parse_eml.py", *dry_run_flag), args.verbose)

    classify_flags = [*dry_run_flag]
    if args.force_classify:
        classify_flags.append("--force")
    run_step(
        "classify_emails",
        step_command("classify_json.py", *classify_flags),
        args.verbose,
        requires_ollama=True,
    )

    extract_flags = [*dry_run_flag]
    if args.force_extract:
        extract_flags.append("--force")
    run_step(
        "extract_email_entities",
        step_command("extract_entities.py", *extract_flags),
        args.verbose,
        requires_ollama=True,
    )

    run_step(
        "parse_jd",
        step_command("parse_jd.py", *dry_run_flag),
        args.verbose,
    )

    run_step(
        "append_entity_aliases",
        step_command("append_aliases.py", *dry_run_flag),
        args.verbose,
    )


if __name__ == "__main__":
    main()
