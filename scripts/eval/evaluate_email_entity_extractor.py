from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from heardbackyet.constants import ALLOWED_CATEGORY_LABELS, APPLICATION_PROGRESS_LABELS
from heardbackyet.paths import EML_PARSED_DIR, PROJECT_ROOT


REQUIRED_COLUMNS = ("email", "expected_label", "expected_entities")
OUTPUT_COLUMNS = (
    "section",
    "label",
    "expected",
    "expected_share",
    "predicted",
    "correct",
    "precision",
    "recall",
    "f1",
)


@dataclass(frozen=True)
class EntityEvaluation:
    entity_name: str
    comparison_path: Path
    metrics_path: Path


EVALUATIONS = (
    EntityEvaluation(
        entity_name="company",
        comparison_path=PROJECT_ROOT / "data" / "eval" / "company_comparison.csv",
        metrics_path=PROJECT_ROOT / "data" / "eval" / "company_metrics.csv",
    ),
    EntityEvaluation(
        entity_name="position",
        comparison_path=PROJECT_ROOT / "data" / "eval" / "position_comparison.csv",
        metrics_path=PROJECT_ROOT / "data" / "eval" / "position_metrics.csv",
    ),
)


def load_selected_raw(path: Path, entity_name: str) -> str:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        return ""

    entity = data.get(entity_name)
    if not isinstance(entity, dict):
        return ""

    selected = entity.get("selected")
    if not isinstance(selected, dict):
        return ""

    raw = selected.get("raw")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return ""


def build_prediction_index(json_dir: Path, entity_name: str) -> dict[str, str]:
    if not json_dir.is_dir():
        raise FileNotFoundError(f"Parsed email JSON directory does not exist: {json_dir}")

    predictions: dict[str, str] = {}
    duplicate_keys: set[str] = set()

    for path in sorted(json_dir.glob("*.json")):
        # Stable email identifiers are the sanitized prefix before the title separator.
        email_id = path.stem.split(" - ", 1)[0]
        if email_id in predictions:
            duplicate_keys.add(email_id)
            continue
        predictions[email_id] = load_selected_raw(path, entity_name)

    for key in duplicate_keys:
        predictions.pop(key, None)

    return predictions


def parse_expected_entities(value: Any, row_number: int) -> list[str]:
    try:
        entities = json.loads(str(value))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Row {row_number}: expected_entities must be a valid JSON array"
        ) from error

    if not isinstance(entities, list):
        raise ValueError(f"Row {row_number}: expected_entities must be a JSON array")
    if any(not isinstance(entity, str) for entity in entities):
        raise ValueError(
            f"Row {row_number}: every expected_entities item must be a string"
        )

    cleaned = [entity.strip() for entity in entities]
    if any(not entity for entity in cleaned):
        raise ValueError(f"Row {row_number}: expected_entities cannot contain blank strings")
    return cleaned


def read_eval_frame(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation CSV does not exist: {path}")

    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Evaluation CSV missing columns: {', '.join(missing_columns)}")

    for column in ("predicted_entity", "is_matched"):
        if column not in frame.columns:
            frame[column] = ""

    frame["_expected_set"] = [
        parse_expected_entities(value, row_number)
        for row_number, value in enumerate(frame["expected_entities"], start=2)
    ]
    return frame


def update_predictions(frame: pd.DataFrame, predictions: dict[str, str]) -> int:
    email_ids = frame["email"].str.strip()
    has_json = email_ids.isin(predictions)

    frame["predicted_entity"] = ""
    frame["is_matched"] = ""

    predicted = email_ids.map(predictions).fillna("")
    frame.loc[has_json, "predicted_entity"] = predicted[has_json]

    for index in frame.index[has_json]:
        expected_entities = frame.at[index, "_expected_set"]
        predicted_entity = frame.at[index, "predicted_entity"]
        # A present entity must match one accepted raw exactly; [] expects no entity.
        is_matched = (
            predicted_entity in expected_entities
            if expected_entities
            else predicted_entity == ""
        )
        frame.at[index, "is_matched"] = "TRUE" if is_matched else "FALSE"

    return int(has_json.sum())


def write_eval_frame(path: Path, frame: pd.DataFrame) -> None:
    output = frame.drop(columns=["_expected_set"])
    output.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")


def safe_divide(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def build_metric_row(
    section: str,
    label: str,
    expected: int,
    predicted: int,
    correct: int,
    total_expected: int,
) -> dict[str, float | int | str | None]:
    precision = None if predicted == 0 else safe_divide(correct, predicted)
    recall = None if expected == 0 else safe_divide(correct, expected)
    f1 = None if expected + predicted == 0 else safe_divide(2 * correct, predicted + expected)

    return {
        "section": section,
        "label": label,
        "expected": expected,
        "expected_share": safe_divide(expected, total_expected),
        "predicted": predicted,
        "correct": correct,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def count_entities(frame: pd.DataFrame) -> tuple[int, int, int]:
    expected_positive = frame["_expected_set"].map(bool)
    predicted_positive = frame["predicted_entity"].str.strip().ne("")
    # True negatives remain visible in is_matched but do not inflate P/R/F1.
    correct = expected_positive & frame["is_matched"].eq("TRUE")
    return (
        int(expected_positive.sum()),
        int(predicted_positive.sum()),
        int(correct.sum()),
    )


def append_label_rows(
    metrics_rows: list[dict[str, float | int | str | None]],
    frame: pd.DataFrame,
    section: str,
    labels: tuple[str, ...],
    total_expected: int,
) -> None:
    expected_labels = frame["expected_label"].str.strip()
    for label in labels:
        expected, predicted, correct = count_entities(frame.loc[expected_labels.eq(label)])
        metrics_rows.append(
            build_metric_row(section, label, expected, predicted, correct, total_expected)
        )


def append_group_row(
    metrics_rows: list[dict[str, float | int | str | None]],
    frame: pd.DataFrame,
    section: str,
    label: str,
    labels: tuple[str, ...],
    total_expected: int,
) -> None:
    expected_labels = frame["expected_label"].str.strip()
    expected, predicted, correct = count_entities(frame.loc[expected_labels.isin(labels)])
    metrics_rows.append(
        build_metric_row(section, label, expected, predicted, correct, total_expected)
    )


def calculate_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    expected_labels = frame["expected_label"].str.strip()
    status_labels = tuple(APPLICATION_PROGRESS_LABELS)
    non_status_labels = tuple(
        label
        for label in ALLOWED_CATEGORY_LABELS
        if label not in APPLICATION_PROGRESS_LABELS
    )
    extra_labels = sorted(
        set(expected_labels[expected_labels.ne("")]) - set(ALLOWED_CATEGORY_LABELS)
    )
    non_status_labels = non_status_labels + tuple(extra_labels)

    metrics_rows: list[dict[str, float | int | str | None]] = []
    total_expected, _, _ = count_entities(frame)
    append_label_rows(
        metrics_rows,
        frame,
        "Status-driving labels",
        status_labels,
        total_expected,
    )
    append_group_row(
        metrics_rows,
        frame,
        "Status-driving labels",
        "subtotal",
        status_labels,
        total_expected,
    )
    append_label_rows(
        metrics_rows,
        frame,
        "Non-status-driving labels",
        non_status_labels,
        total_expected,
    )
    append_group_row(
        metrics_rows,
        frame,
        "Non-status-driving labels",
        "subtotal",
        non_status_labels,
        total_expected,
    )
    append_group_row(
        metrics_rows,
        frame,
        "Overall",
        "overall",
        status_labels + non_status_labels,
        total_expected,
    )

    return pd.DataFrame(metrics_rows, columns=OUTPUT_COLUMNS)


def write_metrics(path: Path, metrics: pd.DataFrame) -> None:
    metrics.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.4f",
        na_rep="N/A",
    )


def print_metrics_table(entity_name: str, metrics: pd.DataFrame) -> None:
    display_columns = [column for column in OUTPUT_COLUMNS if column != "section"]
    formatters = {
        "expected_share": "{:.4f}".format,
        "precision": "{:.4f}".format,
        "recall": "{:.4f}".format,
        "f1": "{:.4f}".format,
    }
    print(f"{entity_name.capitalize()} entity extraction")
    for section, section_frame in metrics.groupby("section", sort=False):
        print(section)
        print(
            section_frame[display_columns].to_string(
                index=False,
                formatters=formatters,
                na_rep="N/A",
            )
        )
        print()


def evaluate_entity(evaluation: EntityEvaluation) -> None:
    predictions = build_prediction_index(EML_PARSED_DIR, evaluation.entity_name)
    frame = read_eval_frame(evaluation.comparison_path)
    matched_json_count = update_predictions(frame, predictions)
    write_eval_frame(evaluation.comparison_path, frame)

    metrics = calculate_metrics(frame)
    write_metrics(evaluation.metrics_path, metrics)
    print_metrics_table(evaluation.entity_name, metrics)
    print(f"Updated rows with matched JSON: {matched_json_count}/{len(frame)}")
    print(f"Wrote metrics: {evaluation.metrics_path}")
    print()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    for evaluation in EVALUATIONS:
        evaluate_entity(evaluation)


if __name__ == "__main__":
    main()
