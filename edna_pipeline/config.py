"""Configuration management for the eDNA analysis pipeline."""

import yaml
from typing import Dict, Any, Optional
from pathlib import Path
import os


class Config:
    """Configuration manager for the eDNA analysis pipeline."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Path to YAML configuration file. If None, uses default config.
        """
        self.config_path = config_path
        self.config = self._load_default_config()
        
        if config_path and os.path.exists(config_path):
            self._load_config_file(config_path)
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load default configuration values."""
        return {
            # Data preprocessing settings
            "preprocessing": {
                "quality_threshold": 20,
                "min_length": 100,
                "max_length": 2000,
                "max_expected_errors": 2,
                "trim_primers": True,
                "remove_chimeras": True,
                "denoise_method": "dada2"  # or "deblur"
            },
            
            # Feature engineering settings
            "feature_engineering": {
                "kmer_size": [3, 4, 5, 6],
                "use_composition": True,
                "use_embeddings": True,
                "embedding_dim": 128,
                "max_sequence_length": 1000
            },
            
            # Model settings
            "models": {
                "supervised": {
                    "model_type": "ensemble",  # "cnn", "lstm", "transformer", "ensemble"
                    "batch_size": 32,
                    "epochs": 100,
                    "learning_rate": 0.001,
                    "dropout": 0.3,
                    "use_gpu": True
                },
                "unsupervised": {
                    "clustering_method": "hdbscan",  # "hdbscan", "dbscan", "kmeans"
                    "min_cluster_size": 10,
                    "dimensionality_reduction": "umap",  # "umap", "tsne", "pca"
                    "n_components": 50
                }
            },
            
            # Taxonomy settings
            "taxonomy": {
                "confidence_threshold": 0.7,
                "hierarchical_levels": ["domain", "phylum", "class", "order", "family", "genus", "species"],
                "novel_taxa_threshold": 0.5
            },
            
            # Abundance settings
            "abundance": {
                "normalization_method": "rarefaction",  # "rarefaction", "relative", "tpm"
                "rarefaction_depth": 10000,
                "calculate_diversity": True,
                "diversity_metrics": ["shannon", "simpson", "chao1"]
            },
            
            # Visualization settings
            "visualization": {
                "plot_format": "png",
                "dpi": 300,
                "figure_size": [12, 8],
                "color_palette": "viridis",
                "interactive": True
            },
            
            # Computational settings
            "computational": {
                "n_jobs": -1,  # -1 for all available cores
                "use_gpu": True,
                "memory_limit": "16GB",
                "chunk_size": 1000
            },
            
            # Output settings
            "output": {
                "save_intermediate": True,
                "output_formats": ["csv", "json", "hdf5"],
                "generate_report": True,
                "log_level": "INFO"
            }
        }
    
    def _load_config_file(self, config_path: str):
        """Load configuration from YAML file."""
        with open(config_path, 'r') as f:
            file_config = yaml.safe_load(f)
        
        # Deep merge with default config
        self.config = self._deep_merge(self.config, file_config)
    
    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., 'models.supervised.batch_size')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """
        Set configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., 'models.supervised.batch_size')
            value: Value to set
        """
        keys = key.split('.')
        config_dict = self.config
        
        for k in keys[:-1]:
            if k not in config_dict:
                config_dict[k] = {}
            config_dict = config_dict[k]
        
        config_dict[keys[-1]] = value
    
    def save(self, output_path: str):
        """
        Save current configuration to YAML file.
        
        Args:
            output_path: Path to save configuration file
        """
        with open(output_path, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False, indent=2)
    
    def to_dict(self) -> Dict[str, Any]:
        """Return configuration as dictionary."""
        return self.config.copy()