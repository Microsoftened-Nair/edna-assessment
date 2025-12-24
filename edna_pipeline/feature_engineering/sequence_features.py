"""Sequence composition and one-hot encoding features."""

import numpy as np
from typing import List, Dict, Union, Tuple
from collections import Counter
from Bio.SeqRecord import SeqRecord
from Bio.SeqUtils import molecular_weight
from Bio.Seq import Seq
import logging

logger = logging.getLogger(__name__)


class SequenceFeatureExtractor:
    """Extract various sequence composition and structural features."""
    
    def __init__(self, config: Dict):
        """
        Initialize sequence feature extractor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.max_sequence_length = config.get("max_sequence_length", 1000)
        self.use_composition = config.get("use_composition", True)
        self.use_one_hot = config.get("use_one_hot", True)
        self.nucleotide_order = ['A', 'C', 'G', 'T']
        
        logger.info("Initialized sequence feature extractor")
    
    def extract_composition_features(self, sequences: List[Union[str, SeqRecord]]) -> np.ndarray:
        """
        Extract sequence composition features.
        
        Args:
            sequences: List of sequences
            
        Returns:
            Composition feature matrix (n_sequences x n_composition_features)
        """
        features = []
        
        for seq in sequences:
            seq_str = str(seq.seq).upper() if isinstance(seq, SeqRecord) else str(seq).upper()
            
            # Basic composition features
            comp_features = self._calculate_composition_features(seq_str)
            features.append(comp_features)
        
        feature_matrix = np.array(features)
        logger.info(f"Extracted composition features: {feature_matrix.shape}")
        
        return feature_matrix
    
    def _calculate_composition_features(self, sequence: str) -> List[float]:
        """Calculate composition features for a single sequence."""
        features = []
        seq_len = len(sequence)
        
        if seq_len == 0:
            return [0.0] * 23  # Return zeros for all features
        
        # 1. Nucleotide frequencies (4 features)
        for nucleotide in self.nucleotide_order:
            count = sequence.count(nucleotide)
            frequency = count / seq_len
            features.append(frequency)
        
        # 2. GC content (1 feature)
        gc_content = (sequence.count('G') + sequence.count('C')) / seq_len
        features.append(gc_content)
        
        # 3. AT content (1 feature)
        at_content = (sequence.count('A') + sequence.count('T')) / seq_len
        features.append(at_content)
        
        # 4. Dinucleotide frequencies (16 features)
        dinuc_features = self._calculate_dinucleotide_frequencies(sequence)
        features.extend(dinuc_features)
        
        # 5. Sequence length (1 feature, normalized)
        normalized_length = min(seq_len / self.max_sequence_length, 1.0)
        features.append(normalized_length)
        
        return features
    
    def _calculate_dinucleotide_frequencies(self, sequence: str) -> List[float]:
        """Calculate dinucleotide frequencies."""
        if len(sequence) < 2:
            return [0.0] * 16
        
        # Count dinucleotides
        dinuc_counts = Counter()
        for i in range(len(sequence) - 1):
            dinuc = sequence[i:i+2]
            if all(base in self.nucleotide_order for base in dinuc):
                dinuc_counts[dinuc] += 1
        
        # Calculate frequencies
        total_dinucs = sum(dinuc_counts.values())
        frequencies = []
        
        for nuc1 in self.nucleotide_order:
            for nuc2 in self.nucleotide_order:
                dinuc = nuc1 + nuc2
                count = dinuc_counts.get(dinuc, 0)
                frequency = count / total_dinucs if total_dinucs > 0 else 0.0
                frequencies.append(frequency)
        
        return frequencies
    
    def extract_one_hot_features(self, sequences: List[Union[str, SeqRecord]], 
                                max_length: int = None) -> np.ndarray:
        """
        Extract one-hot encoded features for sequences.
        
        Args:
            sequences: List of sequences
            max_length: Maximum sequence length (pad/truncate to this length)
            
        Returns:
            One-hot encoded array (n_sequences x max_length x 4)
        """
        if max_length is None:
            max_length = self.max_sequence_length
        
        n_sequences = len(sequences)
        one_hot_matrix = np.zeros((n_sequences, max_length, 4))
        
        nucleotide_to_idx = {nuc: idx for idx, nuc in enumerate(self.nucleotide_order)}
        
        for seq_idx, seq in enumerate(sequences):
            seq_str = str(seq.seq).upper() if isinstance(seq, SeqRecord) else str(seq).upper()
            
            # Truncate or pad sequence
            if len(seq_str) > max_length:
                seq_str = seq_str[:max_length]
            
            # One-hot encode
            for pos, nucleotide in enumerate(seq_str):
                if pos >= max_length:
                    break
                if nucleotide in nucleotide_to_idx:
                    one_hot_matrix[seq_idx, pos, nucleotide_to_idx[nucleotide]] = 1.0
        
        logger.info(f"Extracted one-hot features: {one_hot_matrix.shape}")
        return one_hot_matrix
    
    def extract_structural_features(self, sequences: List[Union[str, SeqRecord]]) -> np.ndarray:
        """
        Extract structural features of sequences.
        
        Args:
            sequences: List of sequences
            
        Returns:
            Structural feature matrix
        """
        features = []
        
        for seq in sequences:
            seq_str = str(seq.seq).upper() if isinstance(seq, SeqRecord) else str(seq).upper()
            
            # Calculate structural features
            struct_features = self._calculate_structural_features(seq_str)
            features.append(struct_features)
        
        feature_matrix = np.array(features)
        logger.info(f"Extracted structural features: {feature_matrix.shape}")
        
        return feature_matrix
    
    def _calculate_structural_features(self, sequence: str) -> List[float]:
        """Calculate structural features for a single sequence."""
        features = []
        
        if len(sequence) == 0:
            return [0.0] * 8  # Return zeros for all features
        
        # 1. Purine content (A, G)
        purine_count = sequence.count('A') + sequence.count('G')
        purine_content = purine_count / len(sequence)
        features.append(purine_content)
        
        # 2. Pyrimidine content (C, T)
        pyrimidine_count = sequence.count('C') + sequence.count('T')
        pyrimidine_content = pyrimidine_count / len(sequence)
        features.append(pyrimidine_content)
        
        # 3. Strong bonds (G, C)
        strong_bonds = (sequence.count('G') + sequence.count('C')) / len(sequence)
        features.append(strong_bonds)
        
        # 4. Weak bonds (A, T)
        weak_bonds = (sequence.count('A') + sequence.count('T')) / len(sequence)
        features.append(weak_bonds)
        
        # 5. Molecular weight (normalized)
        try:
            mol_weight = molecular_weight(sequence, seq_type='DNA')
            # Normalize by sequence length
            normalized_weight = mol_weight / len(sequence) / 330  # Average nucleotide weight ~330
        except:
            normalized_weight = 1.0  # Default value
        features.append(normalized_weight)
        
        # 6. Complexity measures
        complexity = self._calculate_sequence_complexity(sequence)
        features.append(complexity)
        
        # 7. Repetitive elements
        repetitiveness = self._calculate_repetitiveness(sequence)
        features.append(repetitiveness)
        
        # 8. Homopolymer runs
        max_homopolymer = self._calculate_max_homopolymer(sequence)
        features.append(max_homopolymer / len(sequence))  # Normalize by length
        
        return features
    
    def _calculate_sequence_complexity(self, sequence: str) -> float:
        """Calculate sequence complexity using Shannon entropy."""
        if len(sequence) == 0:
            return 0.0
        
        # Count nucleotides
        counts = Counter(sequence)
        total = len(sequence)
        
        # Calculate Shannon entropy
        entropy = 0.0
        for count in counts.values():
            if count > 0:
                p = count / total
                entropy -= p * np.log2(p)
        
        # Normalize by maximum entropy (log2(4) for 4 nucleotides)
        max_entropy = np.log2(4)
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
        
        return normalized_entropy
    
    def _calculate_repetitiveness(self, sequence: str) -> float:
        """Calculate sequence repetitiveness."""
        if len(sequence) < 4:
            return 0.0
        
        # Look for 2-mer and 3-mer repeats
        repeat_count = 0
        total_positions = 0
        
        # 2-mer repeats
        for i in range(len(sequence) - 3):
            dimer = sequence[i:i+2]
            if sequence[i+2:i+4] == dimer:
                repeat_count += 1
            total_positions += 1
        
        # 3-mer repeats
        for i in range(len(sequence) - 5):
            trimer = sequence[i:i+3]
            if sequence[i+3:i+6] == trimer:
                repeat_count += 1
        
        return repeat_count / total_positions if total_positions > 0 else 0.0
    
    def _calculate_max_homopolymer(self, sequence: str) -> int:
        """Calculate the length of the longest homopolymer run."""
        if len(sequence) == 0:
            return 0
        
        max_run = 1
        current_run = 1
        
        for i in range(1, len(sequence)):
            if sequence[i] == sequence[i-1]:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 1
        
        return max_run
    
    def get_composition_feature_names(self) -> List[str]:
        """Get names of composition features."""
        names = []
        
        # Nucleotide frequencies
        for nuc in self.nucleotide_order:
            names.append(f"{nuc}_frequency")
        
        # GC and AT content
        names.extend(["GC_content", "AT_content"])
        
        # Dinucleotide frequencies
        for nuc1 in self.nucleotide_order:
            for nuc2 in self.nucleotide_order:
                names.append(f"{nuc1}{nuc2}_frequency")
        
        # Sequence length
        names.append("normalized_length")
        
        return names
    
    def get_structural_feature_names(self) -> List[str]:
        """Get names of structural features."""
        return [
            "purine_content",
            "pyrimidine_content", 
            "strong_bonds",
            "weak_bonds",
            "normalized_molecular_weight",
            "sequence_complexity",
            "repetitiveness",
            "max_homopolymer_ratio"
        ]
    
    def transform_sequences(self, sequences: List[Union[str, SeqRecord]]) -> Dict[str, np.ndarray]:
        """
        Transform sequences to various feature representations.
        
        Args:
            sequences: List of sequences
            
        Returns:
            Dictionary with different feature types
        """
        features = {}
        
        if self.use_composition:
            features["composition"] = self.extract_composition_features(sequences)
            features["structural"] = self.extract_structural_features(sequences)
        
        if self.use_one_hot:
            features["one_hot"] = self.extract_one_hot_features(sequences)
        
        return features
    
    def get_sequence_statistics(self, sequences: List[Union[str, SeqRecord]]) -> Dict[str, float]:
        """
        Calculate summary statistics for a set of sequences.
        
        Args:
            sequences: List of sequences
            
        Returns:
            Dictionary with sequence statistics
        """
        seq_strings = []
        for seq in sequences:
            seq_str = str(seq.seq).upper() if isinstance(seq, SeqRecord) else str(seq).upper()
            seq_strings.append(seq_str)
        
        if not seq_strings:
            return {}
        
        lengths = [len(seq) for seq in seq_strings]
        gc_contents = []
        complexities = []
        
        for seq_str in seq_strings:
            gc = (seq_str.count('G') + seq_str.count('C')) / len(seq_str)
            gc_contents.append(gc * 100.0) # Multiply by 100 to keep the original unit (percentage) for consistency with Bio.SeqUtils.GC output if it worked
            
            complexity = self._calculate_sequence_complexity(seq_str)
            complexities.append(complexity)
        
        stats = {
            "total_sequences": len(seq_strings),
            "mean_length": np.mean(lengths),
            "std_length": np.std(lengths),
            "min_length": np.min(lengths),
            "max_length": np.max(lengths),
            "mean_gc_content": np.mean(gc_contents),
            "std_gc_content": np.std(gc_contents),
            "mean_complexity": np.mean(complexities),
            "std_complexity": np.std(complexities)
        }
        
        return stats