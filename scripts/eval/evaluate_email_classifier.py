from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
SCRIPT_ROOT = REPO_ROOT / "scripts"

if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import pandas as pd

from constants import ALLOWED_CATEGORY_LABELS, APPLICATION_PROGRESS_LABELS
from paths import EML_PARSED_DIR, PROJECT_ROOT


EVAL_CSV_PATH = PROJECT_ROOT / "data" / "eval" / "label_comparison.csv"
METRICS_CSV_PATH = PROJECT_ROOT / "data" / "eval" / "label_metrics.csv"
REQUIRED_COLUMNS = ("email", "expected_label")
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


def load_json_label(path: Path) -> str | None:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        return None

    category = data.get("category")
    if not isinstance(category, dict):
        return None

    label = category.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return None


def build_prediction_index(json_dir: Path) -> dict[str, str]:
    if not json_dir.is_dir():
        raise FileNotFoundError(f"Parsed email JSON directory does not exist: {json_dir}")

    predictions: dict[str, str] = {}
    duplicate_keys: set[str] = set()

    for path in sorted(json_dir.glob("*.json")):
        # Stable email identifiers are the sanitized prefix before the title separator.
        email_id = path.stem.split(" - ", 1)[0]
        label = load_json_label(path)
        if label is None:
            continue
        if email_id in predictions:
            duplicate_keys.add(email_id)
            continue
        predictions[email_id] = label

    for key in duplicate_keys:
        predictions.pop(key, None)

    return predictions


def read_eval_frame(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation CSV does not exist: {path}")

    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Evaluation CSV missing columns: {', '.join(missing_columns)}")

    for column in ("predicted_label", "is_matched"):
        if column not in frame.columns:
            frame[column] = ""

    return frame


def update_predictions(frame: pd.DataFrame, predictions: dict[str, str]) -> int:
    email_ids = frame["email"].str.strip()
    predicted = email_ids.map(predictions)
    matched = predicted.notna()

    frame["predicted_label"] = ""
    frame["is_matched"] = ""
    frame.loc[matched, "predicted_label"] = predicted[matched]

    expected = frame.loc[matched, "expected_label"].str.strip()
    frame.loc[matched, "is_matched"] = predicted[matched].eq(expected).map(
        {True: "TRUE", False: "FALSE"}
    )

    return int(matched.sum())


def write_eval_frame(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")


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
) -> dict[str, float | int | str]:
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


def append_label_rows(
    metrics_rows: list[dict[str, float | int | str]],
    section: str,
    labels: tuple[str, ...],
    expected_counts: pd.Series,
    predicted_counts: pd.Series,
    correct_counts: pd.Series,
    total_expected: int,
) -> None:
    for label in labels:
        expected = int(expected_counts.get(label, 0))
        predicted = int(predicted_counts.get(label, 0))
        correct = int(correct_counts.get(label, 0))
        metrics_rows.append(
            build_metric_row(section, label, expected, predicted, correct, total_expected)
        )


def append_group_row(
    metrics_rows: list[dict[str, float | int | str]],
    section: str,
    label: str,
    labels: tuple[str, ...],
    expected_counts: pd.Series,
    predicted_counts: pd.Series,
    correct_counts: pd.Series,
    total_expected: int,
) -> None:
    expected = int(expected_counts.reindex(labels, fill_value=0).sum())
    predicted = int(predicted_counts.reindex(labels, fill_value=0).sum())
    correct = int(correct_counts.reindex(labels, fill_value=0).sum())
    metrics_rows.append(
        build_metric_row(section, label, expected, predicted, correct, total_expected)
    )


def calculate_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    expected_labels = frame["expected_label"].str.strip()
    predicted_labels = frame["predicted_label"].str.strip()

    expected_counts = expected_labels[expected_labels.ne("")].value_counts()
    predicted_counts = predicted_labels[predicted_labels.ne("")].value_counts()
    correct_labels = expected_labels[
        expected_labels.ne("") & predicted_labels.ne("") & expected_labels.eq(predicted_labels)
    ]
    correct_counts = correct_labels.value_counts()
    status_labels = tuple(APPLICATION_PROGRESS_LABELS)
    non_status_labels = tuple(
        label
        for label in ALLOWED_CATEGORY_LABELS
        if label not in APPLICATION_PROGRESS_LABELS
    )
    extra_labels = sorted(
        (set(expected_counts.index) | set(predicted_counts.index) | set(correct_counts.index))
        - set(ALLOWED_CATEGORY_LABELS)
    )
    non_status_labels = non_status_labels + tuple(extra_labels)

    metrics_rows: list[dict[str, float | int | str]] = []
    total_expected = int(expected_counts.sum())
    append_label_rows(
        metrics_rows,
        "Status-driving labels",
        status_labels,
        expected_counts,
        predicted_counts,
        correct_counts,
        total_expected,
    )
    append_group_row(
        metrics_rows,
        "Status-driving labels",
        "subtotal",
        status_labels,
        expected_counts,
        predicted_counts,
        correct_counts,
        total_expected,
    )
    append_label_rows(
        metrics_rows,
        "Non-status-driving labels",
        non_status_labels,
        expected_counts,
        predicted_counts,
        correct_counts,
        total_expected,
    )
    append_group_row(
        metrics_rows,
        "Non-status-driving labels",
        "subtotal",
        non_status_labels,
        expected_counts,
        predicted_counts,
        correct_counts,
        total_expected,
    )
    append_group_row(
        metrics_rows,
        "Overall",
        "overall",
        status_labels + non_status_labels,
        expected_counts,
        predicted_counts,
        correct_counts,
        total_expected,
    )

    return pd.DataFrame(metrics_rows, columns=OUTPUT_COLUMNS)


def write_metrics(path: Path, metrics: pd.DataFrame) -> None:
    metrics_for_csv = metrics.copy()
    metrics_for_csv.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.4f",
        na_rep="N/A",
    )


def print_metrics_table(metrics: pd.DataFrame) -> None:
    display_columns = [column for column in OUTPUT_COLUMNS if column != "section"]
    formatters = {
        "expected_share": "{:.4f}".format,
        "precision": "{:.4f}".format,
        "recall": "{:.4f}".format,
        "f1": "{:.4f}".format,
    }
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


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    predictions = build_prediction_index(EML_PARSED_DIR)
    frame = read_eval_frame(EVAL_CSV_PATH)
    matched_json_count = update_predictions(frame, predictions)
    write_eval_frame(EVAL_CSV_PATH, frame)

    metrics = calculate_metrics(frame)
    write_metrics(METRICS_CSV_PATH, metrics)
    print_metrics_table(metrics)
    print()
    print(f"Updated rows with matched JSON: {matched_json_count}/{len(frame)}")
    print(f"Wrote metrics: {METRICS_CSV_PATH}")


if __name__ == "__main__":
    main()
