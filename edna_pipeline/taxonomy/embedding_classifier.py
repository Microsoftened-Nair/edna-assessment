"""Embedding-based classification utilities.

This module provides a post-embedding classification stage that accepts
DNABERT2 embedding files (`.npz`) and generates per-sequence classifications.

Two operation modes are supported:
1. Supervised taxonomy classification when a model bundle is available.
2. Unsupervised OTU-like clustering fallback when no bundle is provided.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import joblib
import numpy as np
from sklearn.cluster import MiniBatchKMeans

logger = logging.getLogger(__name__)

TAXONOMIC_RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]


@dataclass
class ClassificationArtifacts:
    detailed_file: str
    summary_file: str
    predictions_file: str


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_taxonomy_label(label: str) -> Dict[str, str]:
    """Parse taxonomy label strings into canonical rank keys.

    Handles common formats:
    - `k__Bacteria;p__Proteobacteria;...`
    - `Bacteria;Proteobacteria;...`
    - `Bacteria Proteobacteria ...` (space-delimited)
    """
    result = {rank: "Unknown" for rank in TAXONOMIC_RANKS}
    if not label:
        return result

    cleaned = str(label).strip()
    if ";" in cleaned:
        parts = [item.strip() for item in cleaned.split(";") if item.strip()]
    else:
        parts = [item.strip() for item in cleaned.split() if item.strip()]

    normalized: List[str] = []
    for token in parts:
        if "__" in token:
            maybe_rank, value = token.split("__", 1)
            maybe_rank = maybe_rank.strip().lower()
            value = value.strip() or "Unknown"
            rank_map = {
                "k": "kingdom",
                "p": "phylum",
                "c": "class",
                "o": "order",
                "f": "family",
                "g": "genus",
                "s": "species",
            }
            rank_key = rank_map.get(maybe_rank)
            if rank_key:
                result[rank_key] = value
                continue
            normalized.append(value)
        else:
            normalized.append(token)

    for idx, value in enumerate(normalized[: len(TAXONOMIC_RANKS)]):
        result[TAXONOMIC_RANKS[idx]] = value or "Unknown"

    return result


class EmbeddingTaxonomyClassifier:
    """Classify embeddings into taxonomy (or OTU clusters as fallback)."""

    def __init__(
        self,
        model_bundle_path: Optional[str] = None,
        confidence_threshold: float = 0.0,
    ):
        self.model_bundle_path = model_bundle_path
        self.confidence_threshold = max(0.0, min(1.0, float(confidence_threshold)))

    def classify_embeddings(
        self,
        embeddings_file: str,
        output_dir: str,
        sample_id: str,
    ) -> Dict[str, Any]:
        npz_path = Path(embeddings_file)
        if not npz_path.exists():
            raise FileNotFoundError(f"Embedding file not found: {npz_path}")

        arrays = np.load(npz_path, allow_pickle=True)
        if "embeddings" not in arrays or "sequence_ids" not in arrays:
            raise ValueError("Embedding NPZ must contain `embeddings` and `sequence_ids` keys")

        embeddings = np.asarray(arrays["embeddings"])
        sequence_ids = [str(value) for value in np.asarray(arrays["sequence_ids"]).tolist()]

        if embeddings.ndim != 2:
            raise ValueError(f"Expected 2D embeddings array, found shape {embeddings.shape}")

        if len(sequence_ids) != embeddings.shape[0]:
            raise ValueError(
                "Mismatch between sequence_ids and embeddings rows: "
                f"{len(sequence_ids)} vs {embeddings.shape[0]}"
            )

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        classifier_bundle = self._load_model_bundle(self.model_bundle_path)
        if classifier_bundle:
            predictions = self._predict_supervised(embeddings, sequence_ids, classifier_bundle)
            mode = "supervised_taxonomy"
            model_descriptor = classifier_bundle.get("bundle_name") or Path(self.model_bundle_path or "").name
        else:
            predictions = self._predict_with_kmeans_fallback(embeddings, sequence_ids)
            mode = "embedding_kmeans_fallback"
            model_descriptor = "MiniBatchKMeans"

        artifacts = self._write_outputs(output_dir_path, sample_id, predictions)
        summary = self._build_summary(predictions, mode=mode, model_descriptor=model_descriptor)

        with open(artifacts.summary_file, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)

        return {
            "classification_mode": mode,
            "classifier": model_descriptor,
            "total_classified": summary["total_classified"],
            "mean_confidence": summary["mean_confidence"],
            "confidence_distribution": summary["confidence_distribution"],
            "phylum_distribution": summary["phylum_distribution"],
            "genus_distribution": summary["genus_distribution"],
            "species_distribution": summary["species_distribution"],
            "detailed_file": artifacts.detailed_file,
            "summary_file": artifacts.summary_file,
            "predictions_file": artifacts.predictions_file,
            "top_predictions": predictions[:20],
        }

    def _load_model_bundle(self, bundle_path: Optional[str]) -> Optional[Dict[str, Any]]:
        if not bundle_path:
            return None

        resolved = Path(bundle_path)
        if not resolved.is_absolute():
            resolved = (Path.cwd() / resolved).resolve()

        if not resolved.exists():
            logger.info("Model bundle not found at %s. Falling back to unsupervised mode.", resolved)
            return None

        data = joblib.load(resolved)
        if not isinstance(data, dict) or "classifier" not in data:
            raise ValueError(
                "Model bundle must be a dict containing at least a `classifier` key."
            )

        data = dict(data)
        data["bundle_name"] = resolved.name
        return data

    def _predict_supervised(
        self,
        embeddings: np.ndarray,
        sequence_ids: Sequence[str],
        bundle: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        classifier = bundle["classifier"]
        raw_predictions = classifier.predict(embeddings)

        if hasattr(classifier, "predict_proba"):
            probabilities = classifier.predict_proba(embeddings)
            confidences = probabilities.max(axis=1)
        else:
            confidences = np.ones(shape=(embeddings.shape[0],), dtype=float) * 0.7

        label_encoder = bundle.get("label_encoder")
        taxonomy_by_label = bundle.get("taxonomy_by_label") or {}

        rows: List[Dict[str, Any]] = []
        for index, pred in enumerate(raw_predictions):
            if label_encoder is not None:
                decoded = str(label_encoder.inverse_transform([pred])[0])
            else:
                decoded = str(pred)

            taxonomy = taxonomy_by_label.get(decoded)
            if not isinstance(taxonomy, dict):
                taxonomy = _parse_taxonomy_label(decoded)

            confidence = _safe_float(confidences[index], default=0.0)
            if confidence < self.confidence_threshold:
                taxonomy = {rank: "Unknown" for rank in TAXONOMIC_RANKS}

            rows.append(
                {
                    "sequence_id": sequence_ids[index],
                    **taxonomy,
                    "confidence": round(confidence * 100.0, 2),
                    "method": "supervised_taxonomy",
                    "predicted_label": decoded,
                }
            )

        return rows

    def _predict_with_kmeans_fallback(
        self,
        embeddings: np.ndarray,
        sequence_ids: Sequence[str],
    ) -> List[Dict[str, Any]]:
        num_sequences = embeddings.shape[0]
        if num_sequences == 1:
            return [
                {
                    "sequence_id": sequence_ids[0],
                    "kingdom": "Unknown",
                    "phylum": "OTU-001",
                    "class": "Unknown",
                    "order": "Unknown",
                    "family": "Unknown",
                    "genus": "OTU-001",
                    "species": "OTU-001",
                    "confidence": 100.0,
                    "method": "embedding_kmeans_fallback",
                    "predicted_label": "OTU-001",
                }
            ]

        cluster_count = max(2, min(12, int(np.sqrt(max(2, num_sequences / 2)))))

        model = MiniBatchKMeans(
            n_clusters=cluster_count,
            random_state=42,
            batch_size=min(512, max(32, num_sequences)),
            n_init=10,
        )
        cluster_ids = model.fit_predict(embeddings)

        distances = model.transform(embeddings)
        rows: List[Dict[str, Any]] = []
        for index, cluster_id in enumerate(cluster_ids):
            cluster_label = f"OTU-{cluster_id + 1:03d}"
            dists = distances[index]
            scaled = np.exp(-dists)
            denom = float(np.sum(scaled)) if float(np.sum(scaled)) > 0 else 1.0
            confidence = float(scaled[cluster_id] / denom)

            rows.append(
                {
                    "sequence_id": sequence_ids[index],
                    "kingdom": "Unknown",
                    "phylum": cluster_label,
                    "class": "Unknown",
                    "order": "Unknown",
                    "family": "Unknown",
                    "genus": cluster_label,
                    "species": cluster_label,
                    "confidence": round(confidence * 100.0, 2),
                    "method": "embedding_kmeans_fallback",
                    "predicted_label": cluster_label,
                }
            )

        return rows

    def _write_outputs(
        self,
        output_dir: Path,
        sample_id: str,
        predictions: List[Dict[str, Any]],
    ) -> ClassificationArtifacts:
        detailed_file = output_dir / f"{sample_id}_taxonomic_classifications.csv"
        predictions_file = output_dir / f"{sample_id}_taxonomic_classifications.json"
        summary_file = output_dir / f"{sample_id}_classification_summary.json"

        with open(detailed_file, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "sequence_id",
                    "kingdom",
                    "phylum",
                    "class",
                    "order",
                    "family",
                    "genus",
                    "species",
                    "confidence",
                    "method",
                    "predicted_label",
                ],
            )
            writer.writeheader()
            writer.writerows(predictions)

        with open(predictions_file, "w", encoding="utf-8") as handle:
            json.dump(predictions, handle, indent=2)

        return ClassificationArtifacts(
            detailed_file=str(detailed_file),
            summary_file=str(summary_file),
            predictions_file=str(predictions_file),
        )

    def _build_summary(
        self,
        predictions: List[Dict[str, Any]],
        *,
        mode: str,
        model_descriptor: str,
    ) -> Dict[str, Any]:
        confidences = [_safe_float(row.get("confidence"), default=0.0) for row in predictions]

        def _distribution(values: Iterable[str], top_n: int = 20) -> Dict[str, int]:
            counter = Counter(item or "Unknown" for item in values)
            return dict(counter.most_common(top_n))

        confidence_buckets = {
            "0-40": 0,
            "40-60": 0,
            "60-80": 0,
            "80-90": 0,
            "90-100": 0,
        }
        for confidence in confidences:
            if confidence < 40:
                confidence_buckets["0-40"] += 1
            elif confidence < 60:
                confidence_buckets["40-60"] += 1
            elif confidence < 80:
                confidence_buckets["60-80"] += 1
            elif confidence < 90:
                confidence_buckets["80-90"] += 1
            else:
                confidence_buckets["90-100"] += 1

        return {
            "total_classified": len(predictions),
            "mean_confidence": round(float(np.mean(confidences)) if confidences else 0.0, 2),
            "classification_mode": mode,
            "classifier": model_descriptor,
            "phylum_distribution": _distribution((row.get("phylum", "Unknown") for row in predictions)),
            "genus_distribution": _distribution((row.get("genus", "Unknown") for row in predictions)),
            "species_distribution": _distribution((row.get("species", "Unknown") for row in predictions)),
            "confidence_distribution": confidence_buckets,
        }
