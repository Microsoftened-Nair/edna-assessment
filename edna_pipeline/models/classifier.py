import logging
from pathlib import Path
from typing import Dict, List, Union, Optional
import numpy as np

try:
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_extraction.text import TfidfTransformer
    from sklearn.metrics import accuracy_score, classification_report, f1_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import LabelEncoder
    SKLEARN_IMPORT_ERROR = None
except ImportError as exc:
    joblib = None
    RandomForestClassifier = None
    TfidfTransformer = None
    accuracy_score = None
    classification_report = None
    f1_score = None
    train_test_split = None
    Pipeline = None
    LabelEncoder = None
    SKLEARN_IMPORT_ERROR = exc

from edna_pipeline.feature_engineering.kmer_features import KmerFeatureExtractor


class RandomForestKmerClassifier:
    """
    ML classifier for taxonomy prediction using Random Forest on k-mer frequency vectors.
    """
    RANK_KEYS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

    def __init__(self, model_path: Path = None, k: int = 4):
        self.logger = logging.getLogger(__name__)
        self.k = k
        self.expected_feature_count = 4 ** k
        self.model_path = Path(model_path) if model_path else None

        try:
            self.extractor = KmerFeatureExtractor(k=k)
        except TypeError:
            self.extractor = KmerFeatureExtractor(
                {
                    "kmer_size": [k],
                    "normalize_kmers": True,
                    "use_reverse_complement": True,
                }
            )

        if hasattr(self.extractor, "feature_names"):
            self.feature_names = list(getattr(self.extractor, "feature_names"))
        elif hasattr(self.extractor, "get_feature_names"):
            feature_names = self.extractor.get_feature_names()
            self.feature_names = [name.split("_")[-1] for name in feature_names if name.startswith(f"kmer_{k}_")]
        else:
            self.feature_names = list(getattr(self.extractor, "kmer_vocabularies", {}).get(k, []))

        self.model = None
        self.label_encoder = None

        if self.model_path:
            self.load_model(self.model_path)

    def _ensure_ml_dependencies(self):
        if SKLEARN_IMPORT_ERROR is not None:
            raise ImportError(
                "scikit-learn and joblib are required for Random Forest ML classification. "
                f"Original import error: {SKLEARN_IMPORT_ERROR}"
            )

    def _extract_feature_vector(self, sequence: str) -> np.ndarray:
        if hasattr(self.extractor, "extract_features"):
            vector = np.asarray(self.extractor.extract_features(sequence))
        else:
            vector = self.extractor.extract_kmer_frequencies([sequence], self.k)[0]

        expected_len = len(self.feature_names) if self.feature_names else self.expected_feature_count
        if vector.shape[0] != expected_len:
            self.logger.warning(
                "K-mer feature length mismatch: vector=%s expected=%s",
                vector.shape[0],
                expected_len,
            )
        return vector

    def _parse_label_to_ranks(self, label: str) -> Dict[str, str]:
        parts = [p.strip() for p in str(label).split(";")]
        parts = parts + ["Unclassified"] * (len(self.RANK_KEYS) - len(parts))
        return {
            rank: (parts[idx] if parts[idx] else "Unclassified")
            for idx, rank in enumerate(self.RANK_KEYS)
        }

    def train(
        self,
        sequences: List[str],
        labels: List[str],
        model_path: Path,
        n_estimators: int = 100,
        random_state: int = 42,
    ) -> Dict[str, Union[float, str, int]]:
        """Train a Random Forest classifier pipeline and persist it."""
        self._ensure_ml_dependencies()

        if len(sequences) != len(labels):
            raise ValueError("sequences and labels must have the same length")
        if len(sequences) < 2:
            raise ValueError("At least two sequences are required for train/test split")

        feature_matrix = np.vstack([self._extract_feature_vector(seq) for seq in sequences])
        label_encoder = LabelEncoder()
        encoded_labels = label_encoder.fit_transform(labels)

        X_train, X_test, y_train, y_test = train_test_split(
            feature_matrix,
            encoded_labels,
            test_size=0.2,
            stratify=encoded_labels if len(np.unique(encoded_labels)) < len(encoded_labels)/2 else None,
            random_state=random_state,
        )

        estimator = RandomForestClassifier(n_estimators=n_estimators, random_state=random_state, n_jobs=-1)

        pipeline = Pipeline(
            [
                ("normalizer", TfidfTransformer(use_idf=False)),
                ("classifier", estimator),
            ]
        )

        pipeline.fit(X_train, y_train)

        y_pred = pipeline.predict(X_test)
        accuracy = float(accuracy_score(y_test, y_pred))
        macro_f1 = float(f1_score(y_test, y_pred, average="macro"))
        report = classification_report(y_test, y_pred, zero_division=0)
        self.logger.info("Random Forest classifier metrics: accuracy=%.4f, macro_f1=%.4f", accuracy, macro_f1)
        self.logger.info("Classification report:\n%s", report)

        model_path = Path(model_path)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"pipeline": pipeline, "encoder": label_encoder}, model_path)

        self.model = pipeline
        self.label_encoder = label_encoder
        self.model_path = model_path

        return {
            "accuracy": accuracy,
            "macro_f1": macro_f1,
            "num_samples": len(sequences),
            "num_features": int(feature_matrix.shape[1]),
            "classifier": "random_forest",
            "model_path": str(model_path),
        }

    def predict(self, sequence: str) -> Dict[str, Union[str, float, List[Dict[str, float]]]]:
        """Predict taxonomy for a single sequence using the trained Random Forest model."""
        if self.model is None or self.label_encoder is None:
            return self._unclassified_result()

        features = self._extract_feature_vector(sequence).reshape(1, -1)
        encoded_pred = self.model.predict(features)
        probabilities = self.model.predict_proba(features)[0]

        label = self.label_encoder.inverse_transform(encoded_pred)[0]
        rank_values = self._parse_label_to_ranks(label)

        confidence_score = float(np.max(probabilities))
        if confidence_score >= 0.90:
            confidence_level = "high"
        elif confidence_score >= 0.70:
            confidence_level = "medium"
        elif confidence_score >= 0.50:
            confidence_level = "low"
        else:
            confidence_level = "very_low"

        top_indices = np.argsort(probabilities)[::-1][:3]
        top_3_predictions = [
            {
                "label": self.label_encoder.inverse_transform([index])[0],
                "probability": float(probabilities[index]),
            }
            for index in top_indices
        ]

        result = {
            **rank_values,
            "confidence_score": confidence_score,
            "confidence_level": confidence_level,
            "method": "random_forest_kmer",
            "model_type": "random_forest",
            "top_3_predictions": top_3_predictions,
        }

        if confidence_level == "very_low":
            result.update({rank: "Unclassified" for rank in self.RANK_KEYS})

        return result

    def _unclassified_result(self) -> Dict[str, Union[str, float, List[Dict[str, float]]]]:
        return {
            "kingdom": "Unclassified",
            "phylum": "Unclassified",
            "class": "Unclassified",
            "order": "Unclassified",
            "family": "Unclassified",
            "genus": "Unclassified",
            "species": "Unclassified",
            "confidence_score": 0.0,
            "confidence_level": "very_low",
            "method": "random_forest_kmer",
            "model_type": "none",
            "top_3_predictions": [],
        }

    def load_model(self, model_path: Path) -> bool:
        self._ensure_ml_dependencies()
        model_path = Path(model_path)
        if not model_path.exists():
            self.model = None
            self.label_encoder = None
            return False

        try:
            loaded = joblib.load(model_path)
            self.model = loaded.get("pipeline")
            self.label_encoder = loaded.get("encoder")
            if self.model is None or self.label_encoder is None:
                raise ValueError("Model bundle missing 'pipeline' or 'encoder'")
            self.model_path = model_path
            return True
        except Exception as exc:
            self.logger.error("Failed to load Random Forest model from %s: %s", model_path, exc)
            self.model = None
            self.label_encoder = None
            return False
