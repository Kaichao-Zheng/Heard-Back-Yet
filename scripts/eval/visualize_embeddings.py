"""Create a static PCA view of retrieval corpus and evaluation queries."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".cache" / "matplotlib"))

import matplotlib
import numpy as np
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"
matplotlib.rcParams["font.family"] = ["Microsoft YaHei", "DejaVu Sans"]
from matplotlib import pyplot as plt
from matplotlib.colors import TABLEAU_COLORS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.config import load_postgres_config
from db.postgres_models import RetrievalChunk
from retrieval.text_embedder import OllamaTextEmbedder, load_embedding_config


DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "eval" / "embedding_space_pca.png"
)

CATEGORY_ORDER = (
    "email_applied",
    "email_assessment",
    "email_rejection",
    "email_others",
    "job_description",
)
CATEGORY_COLORS = dict(zip(CATEGORY_ORDER, TABLEAU_COLORS.values()))
PRIMARY_EMAIL_TYPES = {"applied", "assessment", "rejection"}
QUERY_COLOR = TABLEAU_COLORS["tab:red"]
EVALUATION_QUERIES = (
    ("Broad", "哪些岗位发了评测？"),
    ("Detail", "哪些岗位要求AWS？"),
    ("Irrelevant", "明天会不会下雨？"),
)


@dataclass(frozen=True)
class PcaProjection:
    coordinates: np.ndarray
    mean: np.ndarray
    components: np.ndarray
    explained_variance: tuple[float, float]


def parse_args() -> None:
    argparse.ArgumentParser(
        description=(
            "Project indexed corpus and unfiltered query embeddings to a shared "
            "2D PCA view."
        )
    ).parse_args()


def main() -> None:
    parse_args()
    embedder = OllamaTextEmbedder(load_embedding_config())
    model = embedder.model_ref
    engine = create_engine(load_postgres_config().database_url())

    with Session(engine) as session:
        chunks = load_chunks(session, model)

    projection = fit_pca([chunk.embedding for chunk in chunks])
    points = build_plot_points(chunks, projection.coordinates)

    query_embeddings = embedder.embed([query for _, query in EVALUATION_QUERIES])
    query_coordinates = project_embeddings(query_embeddings, projection)
    query_points = [
        (float(pc1), float(pc2), prompt_type, query)
        for (prompt_type, query), (pc1, pc2) in zip(
            EVALUATION_QUERIES, query_coordinates, strict=True
        )
    ]

    output_path = DEFAULT_OUTPUT_PATH.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_figure(
        points,
        query_points,
        model,
        projection.explained_variance,
        output_path,
    )

    print(f"Wrote {output_path}")


def load_chunks(
    session: Session,
    model: str,
) -> list[RetrievalChunk]:
    chunks = list(
        session.scalars(
            select(RetrievalChunk)
            .where(RetrievalChunk.embedding_model == model)
            .order_by(RetrievalChunk.chunk_id)
        )
    )
    if not chunks:
        raise RuntimeError(
            f"no retrieval chunks found for configured model {model}; "
            "index the corpus first"
        )
    if len(chunks) < 3:
        raise RuntimeError("PCA visualization requires at least three chunks")
    return chunks


def normalize_embeddings(embeddings: list[list[float]]) -> np.ndarray:
    vectors = np.asarray(embeddings, dtype=np.float64)
    if vectors.ndim != 2 or not np.isfinite(vectors).all():
        raise ValueError("embeddings must be a finite two-dimensional matrix")

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("embeddings must not contain zero vectors")
    return vectors / norms


def fit_pca(embeddings: list[list[float]]) -> PcaProjection:
    normalized = normalize_embeddings(embeddings)

    # Normalize before PCA so the projection starts from the angular geometry
    # used by cosine retrieval instead of vector magnitude differences.
    mean = normalized.mean(axis=0, keepdims=True)
    centered = normalized - mean
    left_vectors, singular_values, right_vectors = np.linalg.svd(
        centered, full_matrices=False
    )
    coordinates = left_vectors[:, :2] * singular_values[:2]

    variance = singular_values**2
    total_variance = float(variance.sum())
    if total_variance == 0:
        raise ValueError("embeddings have no variance to visualize")
    explained = variance[:2] / total_variance
    return PcaProjection(
        coordinates=coordinates,
        mean=mean,
        components=right_vectors[:2],
        explained_variance=(float(explained[0]), float(explained[1])),
    )


def project_embeddings(
    embeddings: list[list[float]],
    projection: PcaProjection,
) -> np.ndarray:
    normalized = normalize_embeddings(embeddings)
    if normalized.shape[1] != projection.mean.shape[1]:
        raise ValueError("query and corpus embedding dimensions do not match")
    return (normalized - projection.mean) @ projection.components.T


def build_plot_points(
    chunks: list[RetrievalChunk],
    coordinates: np.ndarray,
) -> list[tuple[float, float, str]]:
    points: list[tuple[float, float, str]] = []
    for chunk, (pc1, pc2) in zip(chunks, coordinates, strict=True):
        if chunk.source_type == "job_description":
            category = "job_description"
        elif chunk.email_type in PRIMARY_EMAIL_TYPES:
            category = f"email_{chunk.email_type}"
        else:
            category = "email_others"
        points.append((float(pc1), float(pc2), category))
    return points


def write_figure(
    points: list[tuple[float, float, str]],
    query_points: list[tuple[float, float, str, str]],
    model: str,
    explained_variance: tuple[float, float],
    output_path: Path,
) -> None:
    figure, axes = plt.subplots(figsize=(12, 8), constrained_layout=True)

    present_categories = {point[2] for point in points}
    for category in CATEGORY_ORDER:
        if category not in present_categories:
            continue
        category_points = [point for point in points if point[2] == category]
        axes.scatter(
            [point[0] for point in category_points],
            [point[1] for point in category_points],
            label=category,
            color=CATEGORY_COLORS[category],
            marker="D" if category == "job_description" else "o",
            s=54,
            alpha=0.82,
            edgecolors=figure.get_facecolor(),
            linewidths=0.7,
            zorder=3,
        )

    axes.scatter(
        [point[0] for point in query_points],
        [point[1] for point in query_points],
        label="evaluation_query",
        facecolors="none",
        edgecolors=QUERY_COLOR,
        marker="o",
        s=170,
        linewidths=2.4,
        zorder=5,
    )
    annotation_layouts = (
        ((-0.20, 0.09), "right"),   # Broad: assessement query
        ((0.10, -0.02), "left"),     # Detail: AWS query
        ((-0.08, -0.03), "right"),   # Irrelevant: weather query
    )
    for (pc1, pc2, prompt_type, query), (offset, alignment) in zip(
        query_points, annotation_layouts, strict=True
    ):
        axes.annotate(
            f"{prompt_type}: {query}",
            xy=(pc1, pc2),
            xytext=offset,
            textcoords="data",
            color=QUERY_COLOR,
            fontsize=9.5,
            fontweight="normal",
            horizontalalignment=alignment,
            arrowprops={
                "arrowstyle": "-",
                "color": QUERY_COLOR,
                "linewidth": 1.0,
            },
            zorder=6,
        )

    email_x = [point[0] for point in points if point[2] != "job_description"]
    job_description_x = [
        point[0] for point in points if point[2] == "job_description"
    ]
    if email_x and job_description_x and max(email_x) < min(job_description_x):
        source_boundary = (max(email_x) + min(job_description_x)) / 2
        axes.axvline(
            source_boundary,
            color=matplotlib.rcParams["axes.edgecolor"],
            linewidth=1.2,
            linestyle=(0, (4, 4)),
            zorder=2,
        )

    axes.set_title(f"Embedding space PCA · {model}", loc="left", pad=14)
    axes.set_xlabel(f"PC1 · {explained_variance[0]:.1%} explained variance")
    axes.set_ylabel(f"PC2 · {explained_variance[1]:.1%} explained variance")
    axes.set_aspect("equal", adjustable="datalim")
    axes.set_axisbelow(True)
    axes.grid(linewidth=0.9, alpha=0.35)
    axes.spines["top"].set_visible(False)
    axes.spines["right"].set_visible(False)
    axes.legend(
        title="Embedding category",
        loc="upper right",
        frameon=False,
    )

    figure.savefig(
        output_path,
        dpi=160,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Creator": "HeardBackYet retrieval evaluation", "Date": None},
    )
    plt.close(figure)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(f"visualize_embeddings.py: error: {exc}") from exc
