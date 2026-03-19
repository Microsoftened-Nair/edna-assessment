import os
import shutil
import tempfile
import pytest
from pathlib import Path

from edna_pipeline.models.classifier import RandomForestKmerClassifier

@pytest.fixture
def temp_model_dir():
    # Make a temporary directory
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    # Tear down
    shutil.rmtree(temp_dir)

def test_random_forest_kmer_classifier_training(temp_model_dir):
    classifier = RandomForestKmerClassifier(k=3)
    
    # Simple sequences
    sequences = [
        "AATTGGCC", "TTAACCGG", "AATTAATT", "GGCCGGCC",
        "AATTGGCC", "TTAACCGG", "AATTAATT", "GGCCGGCC"
    ]
    
    labels = [
        "Group1;A", "Group2;B", "Group1;A", "Group2;B",
        "Group1;A", "Group2;B", "Group1;A", "Group2;B"
    ]
    
    model_path = temp_model_dir / "test_rf_model.joblib"
    
    result = classifier.train(
        sequences=sequences,
        labels=labels,
        model_path=model_path,
        n_estimators=5,
        random_state=42
    )
    
    assert "accuracy" in result
    assert result["num_samples"] == len(sequences)
    assert model_path.exists()
    
    # Test Prediction
    pred = classifier.predict("AATTGGCC")
    assert "kingdom" in pred
    assert pred["confidence_score"] > 0
    assert pred["method"] == "random_forest_kmer"

def test_classifier_loading(temp_model_dir):
    # Just to assert that it loads properly
    classifier_one = RandomForestKmerClassifier(k=3)
    
    sequences = ["AATTGGCC", "GGCCGGCC", "AATTGGCC", "GGCCGGCC"]
    labels = ["X", "Y", "X", "Y"]
    model_path = temp_model_dir / "test_rf_load.joblib"
    
    classifier_one.train(sequences, labels, model_path, n_estimators=5)
    
    # Try loading from disk
    classifier_two = RandomForestKmerClassifier(model_path=model_path, k=3)
    assert getattr(classifier_two, "model", None) is not None
    
    pred = classifier_two.predict("AATTGGCC")
    assert "confidence_score" in pred
