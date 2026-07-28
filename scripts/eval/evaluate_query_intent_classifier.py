from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from heardbackyet.orchestration.intent_classifier import ClassificationOutcome, IntentClassifier
from heardbackyet.paths import PROJECT_ROOT


EVAL_CSV_PATH = PROJECT_ROOT / "data" / "eval" / "intent_comparison.csv"
METRICS_CSV_PATH = PROJECT_ROOT / "data" / "eval" / "intent_metrics.csv"
NULL_VALUE = "null"
INPUT_COLUMNS = (
    "user_query",
    "reference_time",
    "expected_outcome",
    "expected_intent",
    "expected_reason_code",
)
COMPARISON_COLUMNS = (
    "case_id",
    "user_query",
    "reference_time",
    "expected_outcome",
    "expected_intent",
    "expected_reason_code",
    "predicted_outcome",
    "predicted_intent",
    "predicted_reason_code",
    "is_matched",
    "error",
)
METRICS_COLUMNS = (
    "outcome",
    "expected",
    "expected_share",
    "predicted",
    "correct",
    "precision",
    "recall",
    "f1",
)
OUTCOMES = tuple(outcome.value for outcome in ClassificationOutcome)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score saved intent predictions and optionally regenerate them."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate saved model predictions before calculating metrics.",
    )
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"evaluation CSV does not exist: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing = [
            column
            for column in INPUT_COLUMNS
            if column not in (reader.fieldnames or ())
        ]
        if missing:
            raise ValueError(f"evaluation CSV missing columns: {', '.join(missing)}")

        cases: list[dict[str, str]] = []
        for row_number, row in enumerate(reader, start=2):
            case = {
                column: (row.get(column) or "").strip()
                for column in COMPARISON_COLUMNS
            }
            if not case["user_query"] or not case["reference_time"]:
                raise ValueError(f"blank required value on CSV row {row_number}")
            for column in (
                "expected_outcome",
                "expected_intent",
                "expected_reason_code",
                "predicted_intent",
                "predicted_reason_code",
            ):
                if column.startswith("expected_") and not case[column]:
                    raise ValueError(
                        f"blank {column} on CSV row {row_number}; use null"
                    )
                if case[column] == NULL_VALUE:
                    case[column] = ""

            try:
                reference_time = datetime.fromisoformat(
                    case["reference_time"].replace("Z", "+00:00")
                )
            except ValueError as error:
                raise ValueError(
                    f"invalid reference_time on CSV row {row_number}"
                ) from error
            if reference_time.tzinfo is None:
                raise ValueError(
                    f"reference_time must include timezone on CSV row {row_number}"
                )
            case["reference_time"] = reference_time.isoformat()
            if not has_complete_expectation(case):
                raise ValueError(
                    f"incomplete or invalid expectation on CSV row {row_number}"
                )
            cases.append(case)

    if not cases:
        raise ValueError("evaluation CSV contains no cases")
    return cases


def has_complete_expectation(case: dict[str, str]) -> bool:
    outcome = case["expected_outcome"]
    if outcome == "resolved":
        return bool(case["expected_intent"]) and not case["expected_reason_code"]
    if outcome == "direct_answer":
        return not case["expected_intent"] and not case["expected_reason_code"]
    if outcome in {
        "needs_clarification",
        "requires_decomposition",
        "unsupported",
    }:
        return bool(case["expected_reason_code"]) and not case["expected_intent"]
    return False


def evaluate_cases(
    cases: list[dict[str, str]],
    classifier: IntentClassifier,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for case in cases:
        predicted = {
            "outcome": "",
            "intent": "",
            "reason_code": "",
        }
        error_message = ""
        try:
            result = classifier.classify(
                case["user_query"],
                reference_time=datetime.fromisoformat(case["reference_time"]),
            )
            predicted = {
                "outcome": result.outcome.value,
                "intent": result.spec.intent.value if result.spec else "",
                "reason_code": (
                    result.reason_code.value if result.reason_code else ""
                ),
            }
        except Exception as error:  # Keep the remaining model run observable.
            error_message = f"{type(error).__name__}: {error}"

        is_matched = (
            "TRUE"
            if not error_message
            and predicted["outcome"] == case["expected_outcome"]
            and predicted["intent"] == case["expected_intent"]
            and predicted["reason_code"] == case["expected_reason_code"]
            else "FALSE"
        )
        row = {
            **case,
            "predicted_outcome": predicted["outcome"],
            "predicted_intent": predicted["intent"],
            "predicted_reason_code": predicted["reason_code"],
            "is_matched": is_matched,
            "error": error_message,
        }
        rows.append(row)
        print(
            f"{case['case_id']}: "
            f"expected={case['expected_outcome']}/{case['expected_intent'] or '-'}"
            f"/{case['expected_reason_code'] or '-'} "
            f"predicted={predicted['outcome'] or 'error'}/"
            f"{predicted['intent'] or '-'}/{predicted['reason_code'] or '-'} "
            f"matched={is_matched}"
        )
    return rows


def score_saved_cases(cases: list[dict[str, str]]) -> list[dict[str, str]]:
    for row_number, case in enumerate(cases, start=2):
        if not case["predicted_outcome"] and not case["error"]:
            raise ValueError(
                f"missing saved prediction on CSV row {row_number}; rerun with --force"
            )
        case["is_matched"] = (
            "TRUE"
            if not case["error"]
            and case["predicted_outcome"] == case["expected_outcome"]
            and case["predicted_intent"] == case["expected_intent"]
            and case["predicted_reason_code"] == case["expected_reason_code"]
            else "FALSE"
        )
    return cases


def build_metric_row(
    outcome: str,
    expected: int,
    predicted: int,
    correct: int,
    total_expected: int,
) -> dict[str, float | int | str | None]:
    precision = None if predicted == 0 else correct / predicted
    recall = None if expected == 0 else correct / expected
    f1 = None if expected + predicted == 0 else 2 * correct / (expected + predicted)
    return {
        "outcome": outcome,
        "expected": expected,
        "expected_share": expected / total_expected,
        "predicted": predicted,
        "correct": correct,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def calculate_metrics(rows: list[dict[str, str]]) -> pd.DataFrame:
    expected = pd.Series([row["expected_outcome"] for row in rows])
    predicted = pd.Series(
        ["" if row["error"] else row["predicted_outcome"] for row in rows]
    )
    expected_counts = expected.value_counts()
    predicted_counts = predicted[predicted.ne("")].value_counts()
    correct_counts = expected[expected.eq(predicted)].value_counts()
    total_expected = len(rows)

    metrics_rows = [
        build_metric_row(
            outcome,
            int(expected_counts.get(outcome, 0)),
            int(predicted_counts.get(outcome, 0)),
            int(correct_counts.get(outcome, 0)),
            total_expected,
        )
        for outcome in OUTCOMES
    ]
    metrics_rows.append(
        build_metric_row(
            "overall",
            total_expected,
            int(predicted.ne("").sum()),
            int(expected.eq(predicted).sum()),
            total_expected,
        )
    )
    return pd.DataFrame(metrics_rows, columns=METRICS_COLUMNS)


def write_metrics(metrics: pd.DataFrame) -> None:
    metrics.to_csv(
        METRICS_CSV_PATH,
        index=False,
        encoding="utf-8-sig",
        lineterminator="\n",
        float_format="%.4f",
        na_rep="N/A",
    )


def print_metrics(metrics: pd.DataFrame) -> None:
    formatters = {
        "expected_share": "{:.4f}".format,
        "precision": "{:.4f}".format,
        "recall": "{:.4f}".format,
        "f1": "{:.4f}".format,
    }
    print(
        metrics.to_string(
            index=False,
            formatters=formatters,
            na_rep="N/A",
        )
    )
    print()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    try:
        cases = load_cases(EVAL_CSV_PATH)
        if args.force:
            evaluated_rows = evaluate_cases(cases, IntentClassifier())
            with EVAL_CSV_PATH.open(
                "w", encoding="utf-8-sig", newline=""
            ) as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=COMPARISON_COLUMNS,
                    lineterminator="\n",
                )
                writer.writeheader()
                for row in evaluated_rows:
                    csv_row = dict(row)
                    for column in (
                        "expected_outcome",
                        "expected_intent",
                        "expected_reason_code",
                    ):
                        csv_row[column] = csv_row[column] or NULL_VALUE
                    if csv_row["predicted_outcome"] and not csv_row["error"]:
                        for column in (
                            "predicted_outcome",
                            "predicted_intent",
                            "predicted_reason_code",
                        ):
                            csv_row[column] = csv_row[column] or NULL_VALUE
                    writer.writerow(csv_row)
        else:
            evaluated_rows = score_saved_cases(cases)
        metrics = calculate_metrics(evaluated_rows)
        METRICS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_metrics(metrics)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"evaluate_query_intent_classifier failed: {error}", file=sys.stderr)
        return 1

    matched = sum(row["is_matched"] == "TRUE" for row in evaluated_rows)
    print()
    print_metrics(metrics)
    print(f"Exact matches: {matched}/{len(evaluated_rows)}")
    print(f"Comparison: {EVAL_CSV_PATH}")
    print(f"Metrics: {METRICS_CSV_PATH}")
    has_errors = any(row["error"] for row in evaluated_rows)
    return 0 if not has_errors and matched == len(evaluated_rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
