"""K-mer feature extraction for DNA sequences."""

import numpy as np
from typing import List, Dict, Tuple, Union
from collections import Counter, defaultdict
from itertools import product
from Bio.SeqRecord import SeqRecord
import logging

logger = logging.getLogger(__name__)


class KmerFeatureExtractor:
    """Extract k-mer frequency features from DNA sequences."""
    
    def __init__(self, config: Dict):
        """
        Initialize k-mer feature extractor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.kmer_sizes = config.get("kmer_size", [3, 4, 5, 6])
        if isinstance(self.kmer_sizes, int):
            self.kmer_sizes = [self.kmer_sizes]
        
        self.normalize = config.get("normalize_kmers", True)
        self.use_reverse_complement = config.get("use_reverse_complement", True)
        
        # Generate all possible k-mers for each k
        self.kmer_vocabularies = {}
        for k in self.kmer_sizes:
            self.kmer_vocabularies[k] = self._generate_kmer_vocabulary(k)
        
        logger.info(f"Initialized k-mer extractor with k-sizes: {self.kmer_sizes}")
    
    def _generate_kmer_vocabulary(self, k: int) -> List[str]:
        """
        Generate all possible k-mers of length k.
        
        Args:
            k: K-mer length
            
        Returns:
            List of all possible k-mers
        """
        bases = ['A', 'C', 'G', 'T']
        return [''.join(kmer) for kmer in product(bases, repeat=k)]
    
    def extract_kmers_from_sequence(self, sequence: str, k: int) -> List[str]:
        """
        Extract k-mers from a single sequence.
        
        Args:
            sequence: DNA sequence string
            k: K-mer length
            
        Returns:
            List of k-mers
        """
        sequence = sequence.upper()
        kmers = []
        
        for i in range(len(sequence) - k + 1):
            kmer = sequence[i:i+k]
            # Skip k-mers with ambiguous bases
            if 'N' not in kmer and len(set(kmer) - set('ACGT')) == 0:
                kmers.append(kmer)
                
                # Add reverse complement if specified
                if self.use_reverse_complement:
                    rev_comp = self._reverse_complement(kmer)
                    if rev_comp != kmer:  # Avoid duplicates for palindromic k-mers
                        kmers.append(rev_comp)
        
        return kmers
    
    def _reverse_complement(self, sequence: str) -> str:
        """Get reverse complement of DNA sequence."""
        complement = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C'}
        return ''.join(complement[base] for base in reversed(sequence))
    
    def extract_kmer_frequencies(self, sequences: List[Union[str, SeqRecord]], 
                                k: int) -> np.ndarray:
        """
        Extract k-mer frequency vectors for multiple sequences.
        
        Args:
            sequences: List of sequences (strings or SeqRecord objects)
            k: K-mer length
            
        Returns:
            Numpy array of k-mer frequency vectors (n_sequences x n_kmers)
        """
        if k not in self.kmer_vocabularies:
            raise ValueError(f"K-mer size {k} not in initialized vocabularies: {list(self.kmer_vocabularies.keys())}")
        
        vocab = self.kmer_vocabularies[k]
        kmer_to_idx = {kmer: idx for idx, kmer in enumerate(vocab)}
        
        # Convert sequences to strings if needed
        seq_strings = []
        for seq in sequences:
            if isinstance(seq, SeqRecord):
                seq_strings.append(str(seq.seq))
            else:
                seq_strings.append(str(seq))
        
        # Extract k-mer frequencies
        frequency_matrix = np.zeros((len(seq_strings), len(vocab)))
        
        for seq_idx, seq_str in enumerate(seq_strings):
            kmers = self.extract_kmers_from_sequence(seq_str, k)
            kmer_counts = Counter(kmers)
            
            # Convert to frequency vector
            for kmer, count in kmer_counts.items():
                if kmer in kmer_to_idx:
                    frequency_matrix[seq_idx, kmer_to_idx[kmer]] = count
            
            # Normalize by sequence length or total k-mer count
            if self.normalize:
                total_kmers = frequency_matrix[seq_idx].sum()
                if total_kmers > 0:
                    frequency_matrix[seq_idx] /= total_kmers
        
        logger.info(f"Extracted {k}-mer features: {frequency_matrix.shape}")
        return frequency_matrix
    
    def extract_all_kmer_features(self, sequences: List[Union[str, SeqRecord]]) -> np.ndarray:
        """
        Extract k-mer features for all configured k-mer sizes.
        
        Args:
            sequences: List of sequences
            
        Returns:
            Concatenated feature matrix for all k-mer sizes
        """
        feature_matrices = []
        
        for k in self.kmer_sizes:
            kmer_features = self.extract_kmer_frequencies(sequences, k)
            feature_matrices.append(kmer_features)
            logger.debug(f"K={k}: {kmer_features.shape[1]} features")
        
        # Concatenate all k-mer features
        combined_features = np.concatenate(feature_matrices, axis=1)
        logger.info(f"Combined k-mer features shape: {combined_features.shape}")
        
        return combined_features
    
    def get_feature_names(self) -> List[str]:
        """
        Get feature names for all k-mer features.
        
        Returns:
            List of feature names
        """
        feature_names = []
        
        for k in self.kmer_sizes:
            vocab = self.kmer_vocabularies[k]
            for kmer in vocab:
                feature_names.append(f"kmer_{k}_{kmer}")
        
        return feature_names
    
    def get_top_kmers(self, sequences: List[Union[str, SeqRecord]], 
                     k: int, top_n: int = 20) -> List[Tuple[str, float]]:
        """
        Get the most frequent k-mers across all sequences.
        
        Args:
            sequences: List of sequences
            k: K-mer length
            top_n: Number of top k-mers to return
            
        Returns:
            List of (k-mer, frequency) tuples
        """
        all_kmers = []
        
        for seq in sequences:
            seq_str = str(seq.seq) if isinstance(seq, SeqRecord) else str(seq)
            kmers = self.extract_kmers_from_sequence(seq_str, k)
            all_kmers.extend(kmers)
        
        kmer_counts = Counter(all_kmers)
        total_kmers = len(all_kmers)
        
        # Convert to frequencies and get top k-mers
        top_kmers = []
        for kmer, count in kmer_counts.most_common(top_n):
            frequency = count / total_kmers
            top_kmers.append((kmer, frequency))
        
        return top_kmers
    
    def calculate_kmer_diversity(self, sequences: List[Union[str, SeqRecord]]) -> Dict[int, Dict[str, float]]:
        """
        Calculate k-mer diversity metrics for different k-mer sizes.
        
        Args:
            sequences: List of sequences
            
        Returns:
            Dictionary with diversity metrics for each k-mer size
        """
        diversity_metrics = {}
        
        for k in self.kmer_sizes:
            # Collect all k-mers
            all_kmers = []
            for seq in sequences:
                seq_str = str(seq.seq) if isinstance(seq, SeqRecord) else str(seq)
                kmers = self.extract_kmers_from_sequence(seq_str, k)
                all_kmers.extend(kmers)
            
            if not all_kmers:
                diversity_metrics[k] = {
                    'unique_kmers': 0,
                    'total_kmers': 0,
                    'diversity_ratio': 0.0,
                    'shannon_diversity': 0.0
                }
                continue
            
            kmer_counts = Counter(all_kmers)
            unique_kmers = len(kmer_counts)
            total_kmers = len(all_kmers)
            
            # Calculate Shannon diversity
            shannon_diversity = 0.0
            for count in kmer_counts.values():
                p = count / total_kmers
                if p > 0:
                    shannon_diversity -= p * np.log2(p)
            
            diversity_metrics[k] = {
                'unique_kmers': unique_kmers,
                'total_kmers': total_kmers,
                'diversity_ratio': unique_kmers / total_kmers,
                'shannon_diversity': shannon_diversity
            }
        
        return diversity_metrics
    
    def filter_rare_kmers(self, frequency_matrix: np.ndarray, 
                         min_frequency: float = 0.001) -> Tuple[np.ndarray, np.ndarray]:
        """
        Filter out rare k-mers based on minimum frequency threshold.
        
        Args:
            frequency_matrix: K-mer frequency matrix
            min_frequency: Minimum frequency threshold
            
        Returns:
            Tuple of (filtered_matrix, feature_indices)
        """
        # Calculate mean frequency for each k-mer across all sequences
        mean_frequencies = np.mean(frequency_matrix, axis=0)
        
        # Find k-mers above threshold
        keep_indices = np.where(mean_frequencies >= min_frequency)[0]
        
        # Filter matrix
        filtered_matrix = frequency_matrix[:, keep_indices]
        
        logger.info(f"K-mer filtering: kept {len(keep_indices)}/{frequency_matrix.shape[1]} features")
        
        return filtered_matrix, keep_indices
    
    def transform_sequences(self, sequences: List[Union[str, SeqRecord]]) -> Dict[str, np.ndarray]:
        """
        Transform sequences to k-mer feature representations.
        
        Args:
            sequences: List of sequences
            
        Returns:
            Dictionary with k-mer features for each k-size
        """
        features = {}
        
        for k in self.kmer_sizes:
            features[f"kmer_{k}"] = self.extract_kmer_frequencies(sequences, k)
        
        # Also provide combined features
        features["kmer_combined"] = self.extract_all_kmer_features(sequences)
        
        return features