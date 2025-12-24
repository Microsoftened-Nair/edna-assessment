"""Main feature processor integrating all feature extraction methods."""

import numpy as np
from typing import List, Dict, Union, Tuple, Optional
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.decomposition import PCA
from sklearn.feature_selection import SelectKBest, f_classif
from Bio.SeqRecord import SeqRecord
import logging

from .kmer_features import KmerFeatureExtractor
from .sequence_features import SequenceFeatureExtractor
from .embeddings import SequenceEmbedder

logger = logging.getLogger(__name__)


class FeatureProcessor:
    """Main feature processing pipeline integrating all feature extraction methods."""
    
    def __init__(self, config: Dict):
        """
        Initialize feature processor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.feature_config = config.get("feature_engineering", {})
        
        # Initialize feature extractors
        self.kmer_extractor = KmerFeatureExtractor(self.feature_config)
        self.sequence_extractor = SequenceFeatureExtractor(self.feature_config)
        self.embedder = SequenceEmbedder(self.feature_config)
        
        # Feature selection and scaling options
        self.use_scaling = self.feature_config.get("use_scaling", True)
        self.scaling_method = self.feature_config.get("scaling_method", "standard")  # "standard", "minmax"
        self.use_feature_selection = self.feature_config.get("use_feature_selection", False)
        self.feature_selection_k = self.feature_config.get("feature_selection_k", 1000)
        self.use_dimensionality_reduction = self.feature_config.get("use_dimensionality_reduction", False)
        self.n_components = self.feature_config.get("n_components", 50)
        
        # Fitted transformers
        self.scaler = None
        self.feature_selector = None
        self.pca = None
        self.is_fitted = False
        
        logger.info("Initialized feature processor")
    
    def extract_all_features(self, sequences: List[Union[str, SeqRecord]]) -> Dict[str, np.ndarray]:
        """
        Extract all types of features from sequences.
        
        Args:
            sequences: List of sequences
            
        Returns:
            Dictionary with different feature types
        """
        logger.info(f"Extracting features from {len(sequences)} sequences")
        
        features = {}
        
        # K-mer features
        logger.info("Extracting k-mer features")
        kmer_features = self.kmer_extractor.transform_sequences(sequences)
        features.update(kmer_features)
        
        # Sequence composition and structural features
        logger.info("Extracting sequence features")
        seq_features = self.sequence_extractor.transform_sequences(sequences)
        features.update(seq_features)
        
        # Sequence embeddings
        logger.info("Extracting sequence embeddings")
        if self.feature_config.get("use_embeddings", True):
            embedding_features = self.embedder.transform_sequences(sequences)
            features.update(embedding_features)
        
        logger.info(f"Extracted {len(features)} feature types")
        return features
    
    def combine_features(self, feature_dict: Dict[str, np.ndarray], 
                        feature_types: List[str] = None) -> Tuple[np.ndarray, List[str]]:
        """
        Combine different feature types into a single matrix.
        
        Args:
            feature_dict: Dictionary of feature arrays
            feature_types: List of feature types to combine (if None, use all)
            
        Returns:
            Tuple of (combined_feature_matrix, feature_names)
        """
        if feature_types is None:
            feature_types = list(feature_dict.keys())
        
        # Filter out 3D arrays (like one-hot encoding) for now
        matrices_to_combine = []
        feature_names = []
        
        for feature_type in feature_types:
            if feature_type not in feature_dict:
                logger.warning(f"Feature type '{feature_type}' not found in feature dictionary")
                continue
            
            feature_array = feature_dict[feature_type]
            
            # Handle 3D arrays (flatten them)
            if len(feature_array.shape) == 3:
                logger.info(f"Flattening 3D feature array: {feature_type}")
                n_samples = feature_array.shape[0]
                flattened = feature_array.reshape(n_samples, -1)
                matrices_to_combine.append(flattened)
                
                # Generate feature names for flattened array
                for i in range(flattened.shape[1]):
                    feature_names.append(f"{feature_type}_{i}")
            
            # Handle 2D arrays
            elif len(feature_array.shape) == 2:
                matrices_to_combine.append(feature_array)
                
                # Generate feature names
                for i in range(feature_array.shape[1]):
                    feature_names.append(f"{feature_type}_{i}")
            
            else:
                logger.warning(f"Unsupported feature array shape for {feature_type}: {feature_array.shape}")
        
        if not matrices_to_combine:
            raise ValueError("No feature matrices to combine")
        
        # Combine all feature matrices
        combined_features = np.concatenate(matrices_to_combine, axis=1)
        
        logger.info(f"Combined features shape: {combined_features.shape}")
        return combined_features, feature_names
    
    def fit_transforms(self, X: np.ndarray, y: np.ndarray = None) -> np.ndarray:
        """
        Fit and apply feature transformations.
        
        Args:
            X: Feature matrix
            y: Target labels (optional, for supervised feature selection)
            
        Returns:
            Transformed feature matrix
        """
        logger.info("Fitting feature transforms")
        
        X_transformed = X.copy()
        
        # 1. Feature scaling
        if self.use_scaling:
            if self.scaling_method == "standard":
                self.scaler = StandardScaler()
            elif self.scaling_method == "minmax":
                self.scaler = MinMaxScaler()
            else:
                raise ValueError(f"Unknown scaling method: {self.scaling_method}")
            
            X_transformed = self.scaler.fit_transform(X_transformed)
            logger.info(f"Applied {self.scaling_method} scaling")
        
        # 2. Feature selection
        if self.use_feature_selection and y is not None:
            k = min(self.feature_selection_k, X_transformed.shape[1])
            self.feature_selector = SelectKBest(score_func=f_classif, k=k)
            X_transformed = self.feature_selector.fit_transform(X_transformed, y)
            logger.info(f"Selected {k} best features")
        
        # 3. Dimensionality reduction
        if self.use_dimensionality_reduction:
            n_components = min(self.n_components, X_transformed.shape[1])
            self.pca = PCA(n_components=n_components)
            X_transformed = self.pca.fit_transform(X_transformed)
            logger.info(f"Reduced to {n_components} components with PCA")
            
            # Log explained variance ratio
            explained_variance = np.sum(self.pca.explained_variance_ratio_)
            logger.info(f"PCA explained variance ratio: {explained_variance:.3f}")
        
        self.is_fitted = True
        return X_transformed
    
    def transform(self, X: np.ndarray) -> np.ndarray:
        """
        Apply fitted transformations to new data.
        
        Args:
            X: Feature matrix
            
        Returns:
            Transformed feature matrix
        """
        if not self.is_fitted:
            raise ValueError("FeatureProcessor must be fitted before transform")
        
        X_transformed = X.copy()
        
        # Apply transformations in the same order as fit
        if self.scaler is not None:
            X_transformed = self.scaler.transform(X_transformed)
        
        if self.feature_selector is not None:
            X_transformed = self.feature_selector.transform(X_transformed)
        
        if self.pca is not None:
            X_transformed = self.pca.transform(X_transformed)
        
        return X_transformed
    
    def process_sequences(self, sequences: List[Union[str, SeqRecord]], 
                         labels: np.ndarray = None,
                         feature_types: List[str] = None) -> Tuple[np.ndarray, List[str]]:
        """
        Complete feature processing pipeline for sequences.
        
        Args:
            sequences: List of sequences
            labels: Optional labels for supervised feature selection
            feature_types: List of feature types to use
            
        Returns:
            Tuple of (processed_features, feature_names)
        """
        logger.info(f"Processing {len(sequences)} sequences")
        
        # Extract all features
        feature_dict = self.extract_all_features(sequences)
        
        # Combine features
        combined_features, feature_names = self.combine_features(feature_dict, feature_types)
        
        # Apply transformations
        processed_features = self.fit_transforms(combined_features, labels)
        
        # Update feature names if dimensionality changed
        if processed_features.shape[1] != len(feature_names):
            if self.pca is not None:
                feature_names = [f"PC_{i+1}" for i in range(processed_features.shape[1])]
            else:
                feature_names = [f"feature_{i}" for i in range(processed_features.shape[1])]
        
        logger.info(f"Final processed features shape: {processed_features.shape}")
        return processed_features, feature_names
    
    def process_new_sequences(self, sequences: List[Union[str, SeqRecord]],
                            feature_types: List[str] = None) -> np.ndarray:
        """
        Process new sequences using fitted transformations.
        
        Args:
            sequences: List of sequences
            feature_types: List of feature types to use
            
        Returns:
            Processed feature matrix
        """
        if not self.is_fitted:
            raise ValueError("FeatureProcessor must be fitted before processing new sequences")
        
        logger.info(f"Processing {len(sequences)} new sequences")
        
        # Extract features
        feature_dict = self.extract_all_features(sequences)
        
        # Combine features
        combined_features, _ = self.combine_features(feature_dict, feature_types)
        
        # Apply fitted transformations
        processed_features = self.transform(combined_features)
        
        logger.info(f"Processed new sequences shape: {processed_features.shape}")
        return processed_features
    
    def get_feature_importance(self) -> Dict[str, np.ndarray]:
        """
        Get feature importance information from fitted transformers.
        
        Returns:
            Dictionary with feature importance information
        """
        importance_info = {}
        
        # Feature selection scores
        if self.feature_selector is not None:
            importance_info["feature_selection_scores"] = self.feature_selector.scores_
            importance_info["selected_features"] = self.feature_selector.get_support()
        
        # PCA component loadings
        if self.pca is not None:
            importance_info["pca_components"] = self.pca.components_
            importance_info["pca_explained_variance"] = self.pca.explained_variance_ratio_
        
        return importance_info
    
    def save_feature_stats(self, sequences: List[Union[str, SeqRecord]], 
                          output_file: str):
        """
        Save feature statistics to file.
        
        Args:
            sequences: List of sequences
            output_file: Output file path
        """
        # Get sequence statistics
        seq_stats = self.sequence_extractor.get_sequence_statistics(sequences)
        
        # Get k-mer diversity
        kmer_diversity = self.kmer_extractor.calculate_kmer_diversity(sequences)
        
        with open(output_file, 'w') as f:
            f.write("Feature Extraction Statistics\n")
            f.write("=" * 40 + "\n\n")
            
            f.write("Sequence Statistics:\n")
            f.write("-" * 20 + "\n")
            for key, value in seq_stats.items():
                f.write(f"{key}: {value}\n")
            
            f.write("\nK-mer Diversity:\n")
            f.write("-" * 20 + "\n")
            for k, metrics in kmer_diversity.items():
                f.write(f"K={k}:\n")
                for metric, value in metrics.items():
                    f.write(f"  {metric}: {value}\n")
            
            # Add feature processing info if fitted
            if self.is_fitted:
                f.write("\nFeature Processing:\n")
                f.write("-" * 20 + "\n")
                f.write(f"Scaling method: {self.scaling_method if self.scaler else 'None'}\n")
                f.write(f"Feature selection: {self.use_feature_selection}\n")
                if self.feature_selector:
                    f.write(f"Selected features: {np.sum(self.feature_selector.get_support())}\n")
                f.write(f"Dimensionality reduction: {self.use_dimensionality_reduction}\n")
                if self.pca:
                    f.write(f"PCA components: {self.pca.n_components_}\n")
                    f.write(f"Explained variance: {np.sum(self.pca.explained_variance_ratio_):.3f}\n")
        
        logger.info(f"Saved feature statistics to {output_file}")
    
    def get_recommended_feature_types(self, sequences: List[Union[str, SeqRecord]]) -> List[str]:
        """
        Get recommended feature types based on sequence characteristics.
        
        Args:
            sequences: List of sequences
            
        Returns:
            List of recommended feature types
        """
        seq_stats = self.sequence_extractor.get_sequence_statistics(sequences)
        recommended = []
        
        # Always recommend basic features
        recommended.extend(["composition", "structural"])
        
        # Recommend k-mer features based on sequence length and diversity
        if seq_stats.get("mean_length", 0) > 50:
            recommended.extend(["kmer_3", "kmer_4"])
            
            if seq_stats.get("mean_length", 0) > 100:
                recommended.append("kmer_5")
                
            if seq_stats.get("mean_length", 0) > 200:
                recommended.append("kmer_6")
        
        # Recommend embeddings for longer sequences
        if seq_stats.get("mean_length", 0) > 100:
            recommended.append("embeddings")
        
        # Recommend one-hot for shorter sequences or CNN models
        if seq_stats.get("mean_length", 0) < 500:
            recommended.append("one_hot")
        
        logger.info(f"Recommended feature types: {recommended}")
        return recommended