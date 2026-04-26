"""Minimal eDNA pipeline package for pretrained DNABERT2 embedding generation."""

__version__ = "1.0.0"

from .models import DNABERT2EmbeddingsExtractor
from .taxonomy import EmbeddingTaxonomyClassifier
from .visualization import create_classification_html_report

__all__ = [
	"DNABERT2EmbeddingsExtractor",
	"EmbeddingTaxonomyClassifier",
	"create_classification_html_report",
]