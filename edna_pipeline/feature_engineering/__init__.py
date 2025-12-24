"""
Feature engineering module for eDNA sequence analysis.

This module provides functionality for:
- k-mer frequency extraction  
- One-hot encoding of DNA sequences
- Sequence composition analysis (GC content, di-nucleotide frequencies)
- Dimensionality reduction
- Sequence embeddings
"""

from .kmer_features import KmerFeatureExtractor
from .sequence_features import SequenceFeatureExtractor
from .embeddings import SequenceEmbedder
from .feature_processor import FeatureProcessor

__all__ = [
    "KmerFeatureExtractor",
    "SequenceFeatureExtractor", 
    "SequenceEmbedder",
    "FeatureProcessor"
]