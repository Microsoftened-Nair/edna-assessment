"""Denoising algorithms for eDNA sequence analysis."""

import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict
from Bio.SeqRecord import SeqRecord
from Bio.Seq import Seq
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class DenoiseBase(ABC):
    """Base class for denoising algorithms."""
    
    def __init__(self, config: Dict):
        """
        Initialize denoiser.
        
        Args:
            config: Configuration parameters
        """
        self.config = config
        
    @abstractmethod
    def denoise(self, sequences: List[SeqRecord]) -> Tuple[List[SeqRecord], Dict]:
        """
        Denoise sequences to generate ASVs.
        
        Args:
            sequences: Input sequences
            
        Returns:
            Tuple of (ASV sequences, abundance table)
        """
        pass


class DenoiseDADA2(DenoiseBase):
    """DADA2-like denoising algorithm implementation."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.error_rate = config.get("error_rate", 1e-10)
        self.min_abundance = config.get("min_abundance", 2)
        self.max_iterations = config.get("max_iterations", 100)
        self.convergence_threshold = config.get("convergence_threshold", 1e-6)
        
    def denoise(self, sequences: List[SeqRecord]) -> Tuple[List[SeqRecord], Dict]:
        """
        Implement DADA2-like denoising algorithm.
        
        Args:
            sequences: Input sequences
            
        Returns:
            Tuple of (ASV sequences, abundance table)
        """
        logger.info(f"Starting DADA2-like denoising on {len(sequences)} sequences")
        
        # Convert sequences to strings and count abundances
        seq_counts = Counter(str(seq.seq) for seq in sequences)
        
        # Filter by minimum abundance
        seq_counts = {seq: count for seq, count in seq_counts.items() 
                     if count >= self.min_abundance}

        if not seq_counts and sequences:
            logger.warning(
                "No sequences passed min_abundance=%s; relaxing threshold to 1 for %d reads",
                self.min_abundance,
                len(sequences)
            )
            seq_counts = Counter(str(seq.seq) for seq in sequences)
            self.min_abundance = 1
        
        logger.info(f"After abundance filtering: {len(seq_counts)} unique sequences")
        
        # Initialize clusters with each unique sequence as its own cluster
        clusters = self._initialize_clusters(seq_counts)
        
        # Iteratively merge similar sequences
        for iteration in range(self.max_iterations):
            old_clusters = clusters.copy()
            clusters = self._merge_iteration(clusters)
            
            # Check convergence
            if self._check_convergence(old_clusters, clusters):
                logger.info(f"Converged after {iteration + 1} iterations")
                break
        else:
            logger.warning(f"Did not converge after {self.max_iterations} iterations")
        
        # Generate ASVs and abundance table
        asvs, abundance_table = self._generate_output(clusters, seq_counts)
        
        logger.info(f"Generated {len(asvs)} ASVs from denoising")
        
        return asvs, abundance_table
    
    def _initialize_clusters(self, seq_counts: Dict[str, int]) -> List[Dict]:
        """Initialize clusters with each sequence as its own cluster."""
        clusters = []
        for i, (seq, count) in enumerate(seq_counts.items()):
            clusters.append({
                'representative': seq,
                'sequences': [seq],
                'abundance': count,
                'id': f"ASV_{i+1}"
            })
        return clusters
    
    def _merge_iteration(self, clusters: List[Dict]) -> List[Dict]:
        """Perform one iteration of cluster merging."""
        merged_clusters = []
        used_indices = set()
        
        for i, cluster1 in enumerate(clusters):
            if i in used_indices:
                continue
                
            merged_cluster = cluster1.copy()
            merged_cluster['sequences'] = cluster1['sequences'].copy()
            
            for j, cluster2 in enumerate(clusters[i+1:], i+1):
                if j in used_indices:
                    continue
                
                # Check if clusters should be merged
                if self._should_merge(cluster1, cluster2):
                    # Merge clusters
                    merged_cluster['sequences'].extend(cluster2['sequences'])
                    merged_cluster['abundance'] += cluster2['abundance']
                    
                    # Update representative to most abundant sequence
                    seq_abundances = {}
                    for seq in merged_cluster['sequences']:
                        seq_abundances[seq] = seq_abundances.get(seq, 0) + 1
                    
                    merged_cluster['representative'] = max(
                        seq_abundances.keys(), 
                        key=seq_abundances.get
                    )
                    
                    used_indices.add(j)
            
            merged_clusters.append(merged_cluster)
            used_indices.add(i)
        
        return merged_clusters
    
    def _should_merge(self, cluster1: Dict, cluster2: Dict) -> bool:
        """
        Determine if two clusters should be merged based on sequence similarity.
        
        Args:
            cluster1: First cluster
            cluster2: Second cluster
            
        Returns:
            True if clusters should be merged
        """
        seq1 = cluster1['representative']
        seq2 = cluster2['representative']
        
        # Calculate Hamming distance
        if len(seq1) != len(seq2):
            return False
        
        mismatches = sum(c1 != c2 for c1, c2 in zip(seq1, seq2))
        error_rate = mismatches / len(seq1)
        
        # Use abundance-weighted decision
        abundance_factor = min(cluster1['abundance'], cluster2['abundance'])
        threshold = self.error_rate * np.log(abundance_factor + 1)
        
        return error_rate <= threshold
    
    def _check_convergence(self, old_clusters: List[Dict], new_clusters: List[Dict]) -> bool:
        """Check if clustering has converged."""
        if len(old_clusters) != len(new_clusters):
            return False
        
        # Simple convergence check - no changes in cluster composition
        old_reps = set(cluster['representative'] for cluster in old_clusters)
        new_reps = set(cluster['representative'] for cluster in new_clusters)
        
        return old_reps == new_reps
    
    def _generate_output(self, clusters: List[Dict], seq_counts: Dict[str, int]) -> Tuple[List[SeqRecord], Dict]:
        """Generate final ASVs and abundance table."""
        asvs = []
        abundance_table = {}
        
        for cluster in clusters:
            asv_id = cluster['id']
            rep_seq = cluster['representative']
            
            # Create SeqRecord for ASV
            asv_record = SeqRecord(
                Seq(rep_seq),
                id=asv_id,
                description=f"ASV representative sequence, abundance={cluster['abundance']}"
            )
            asvs.append(asv_record)
            
            # Add to abundance table
            abundance_table[asv_id] = cluster['abundance']
        
        return asvs, abundance_table


class DenoiseDeblur(DenoiseBase):
    """Deblur-like denoising algorithm implementation."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.trim_length = config.get("trim_length", 150)
        self.min_reads = config.get("min_reads", 10)
        self.error_profile = config.get("error_profile", None)
        
    def denoise(self, sequences: List[SeqRecord]) -> Tuple[List[SeqRecord], Dict]:
        """
        Implement Deblur-like denoising algorithm.
        
        Args:
            sequences: Input sequences
            
        Returns:
            Tuple of (ASV sequences, abundance table)
        """
        logger.info(f"Starting Deblur-like denoising on {len(sequences)} sequences")
        
        # Trim sequences to uniform length
        trimmed_sequences = self._trim_sequences(sequences)
        
        # Count sequence abundances
        seq_counts = Counter(str(seq.seq) for seq in trimmed_sequences)
        
        # Filter by minimum reads
        seq_counts = {seq: count for seq, count in seq_counts.items() 
                     if count >= self.min_reads}
        
        logger.info(f"After filtering: {len(seq_counts)} unique sequences")
        
        # Remove likely error sequences
        clean_sequences = self._remove_errors(seq_counts)
        
        # Generate ASVs
        asvs, abundance_table = self._generate_asvs(clean_sequences)
        
        logger.info(f"Generated {len(asvs)} ASVs from Deblur denoising")
        
        return asvs, abundance_table
    
    def _trim_sequences(self, sequences: List[SeqRecord]) -> List[SeqRecord]:
        """Trim all sequences to uniform length."""
        trimmed = []
        for seq in sequences:
            if len(seq.seq) >= self.trim_length:
                trimmed_seq = seq[:self.trim_length]
                trimmed.append(trimmed_seq)
        
        logger.info(f"Trimmed {len(trimmed)}/{len(sequences)} sequences to length {self.trim_length}")
        return trimmed
    
    def _remove_errors(self, seq_counts: Dict[str, int]) -> Dict[str, int]:
        """Remove sequences that are likely sequencing errors."""
        clean_sequences = seq_counts.copy()
        
        # Sort sequences by abundance (descending)
        sorted_seqs = sorted(seq_counts.items(), key=lambda x: x[1], reverse=True)
        
        for seq, count in sorted_seqs:
            if seq not in clean_sequences:
                continue
                
            # Look for sequences that might be errors of this sequence
            to_remove = []
            for other_seq, other_count in clean_sequences.items():
                if other_seq == seq or other_count >= count:
                    continue
                
                # Check if other_seq could be an error of seq
                if self._is_likely_error(other_seq, seq, other_count, count):
                    to_remove.append(other_seq)
            
            # Remove error sequences and add their counts to parent
            for error_seq in to_remove:
                if error_seq in clean_sequences:
                    clean_sequences[seq] += clean_sequences[error_seq]
                    del clean_sequences[error_seq]
        
        return clean_sequences
    
    def _is_likely_error(self, error_seq: str, parent_seq: str, 
                        error_count: int, parent_count: int) -> bool:
        """
        Determine if error_seq is likely a sequencing error of parent_seq.
        
        Args:
            error_seq: Potential error sequence
            parent_seq: Potential parent sequence
            error_count: Abundance of error sequence
            parent_count: Abundance of parent sequence
            
        Returns:
            True if error_seq is likely an error of parent_seq
        """
        if len(error_seq) != len(parent_seq):
            return False
        
        # Count mismatches
        mismatches = sum(c1 != c2 for c1, c2 in zip(error_seq, parent_seq))
        
        # Use simple heuristics
        # 1. Only single nucleotide differences
        if mismatches != 1:
            return False
        
        # 2. Error sequence should be much less abundant
        if error_count >= parent_count * 0.1:  # 10% threshold
            return False
        
        return True
    
    def _generate_asvs(self, clean_sequences: Dict[str, int]) -> Tuple[List[SeqRecord], Dict]:
        """Generate ASVs from clean sequences."""
        asvs = []
        abundance_table = {}
        
        for i, (seq, count) in enumerate(clean_sequences.items(), 1):
            asv_id = f"ASV_{i}"
            
            # Create SeqRecord
            asv_record = SeqRecord(
                Seq(seq),
                id=asv_id,
                description=f"Deblur ASV, abundance={count}"
            )
            asvs.append(asv_record)
            
            # Add to abundance table
            abundance_table[asv_id] = count
        
        return asvs, abundance_table