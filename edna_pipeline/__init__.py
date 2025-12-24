"""
AI-Driven Deep-Sea eDNA Analysis Pipeline for Eukaryotic Biodiversity Assessment

This package provides a comprehensive pipeline for analyzing environmental DNA (eDNA)
from deep-sea ecosystems using artificial intelligence and machine learning approaches.

The pipeline addresses the challenge of accurately identifying novel or poorly-represented
deep-sea eukaryotic organisms by minimizing reliance on incomplete reference databases.
"""

__version__ = "1.0.0"
__author__ = "Deep-Sea eDNA Analysis Team"
__email__ = "contact@deep-sea-edna.org"

from .pipeline import DeepSeaEDNAPipeline
from .config import Config

__all__ = ["DeepSeaEDNAPipeline", "Config"]