"""Chimera detection and removal for eDNA sequences."""

import numpy as np
from typing import List, Tuple, Set, Dict
from collections import defaultdict
from Bio.SeqRecord import SeqRecord
import logging

logger = logging.getLogger(__name__)


class ChimeraRemover:
    """Chimera detection and removal for sequence data."""
    
    def __init__(self, config: Dict):
        """
        Initialize chimera remover.
        
        Args:
            config: Configuration parameters
        """
        self.config = config
        self.min_divergence = config.get("min_divergence", 0.3)
        self.min_abundance_ratio = config.get("min_abundance_ratio", 2.0)
        self.window_size = config.get("window_size", 50)
        self.step_size = config.get("step_size", 10)
        
    def remove_chimeras(self, sequences: List[SeqRecord], 
                       abundance_table: Dict[str, int] = None) -> Tuple[List[SeqRecord], Set[str]]:
        """
        Remove chimeric sequences from the dataset.
        
        Args:
            sequences: List of sequence records
            abundance_table: Optional abundance information
            
        Returns:
            Tuple of (non-chimeric sequences, set of chimeric sequence IDs)
        """
        logger.info(f"Starting chimera detection on {len(sequences)} sequences")
        
        # Create abundance table if not provided
        if abundance_table is None:
            abundance_table = {seq.id: 1 for seq in sequences}
        
        # Sort sequences by abundance (most abundant first)
        sorted_sequences = sorted(
            sequences, 
            key=lambda x: abundance_table.get(x.id, 1), 
            reverse=True
        )
        
        chimeric_ids = set()
        non_chimeric = []
        
        for i, query_seq in enumerate(sorted_sequences):
            if query_seq.id in chimeric_ids:
                continue
            
            # Check if current sequence is chimeric
            is_chimeric, parent_info = self._is_chimeric(
                query_seq, 
                non_chimeric,  # Use already confirmed non-chimeric sequences as references
                abundance_table
            )
            
            if is_chimeric:
                chimeric_ids.add(query_seq.id)
                logger.debug(f"Identified chimera: {query_seq.id} (parents: {parent_info})")
            else:
                non_chimeric.append(query_seq)
        
        logger.info(f"Removed {len(chimeric_ids)} chimeric sequences")
        logger.info(f"Retained {len(non_chimeric)} non-chimeric sequences")
        
        return non_chimeric, chimeric_ids
    
    def _is_chimeric(self, query_seq: SeqRecord, reference_seqs: List[SeqRecord],
                    abundance_table: Dict[str, int]) -> Tuple[bool, Dict]:
        """
        Check if a sequence is chimeric using sliding window analysis.
        
        Args:
            query_seq: Sequence to test for chimeric nature
            reference_seqs: Reference sequences to use as potential parents
            abundance_table: Abundance information
            
        Returns:
            Tuple of (is_chimeric, parent_information)
        """
        if len(reference_seqs) < 2:
            return False, {}
        
        query_abundance = abundance_table.get(query_seq.id, 1)
        query_str = str(query_seq.seq)
        
        # Find potential parent pairs
        best_score = 0
        best_parents = None
        
        for i, parent1 in enumerate(reference_seqs):
            parent1_abundance = abundance_table.get(parent1.id, 1)
            
            # Skip if parent1 is not abundant enough
            if parent1_abundance < query_abundance * self.min_abundance_ratio:
                continue
            
            for parent2 in reference_seqs[i+1:]:
                parent2_abundance = abundance_table.get(parent2.id, 1)
                
                # Skip if parent2 is not abundant enough
                if parent2_abundance < query_abundance * self.min_abundance_ratio:
                    continue
                
                # Check for chimeric signature
                score, breakpoint = self._calculate_chimeric_score(
                    query_str, str(parent1.seq), str(parent2.seq)
                )
                
                if score > best_score:
                    best_score = score
                    best_parents = {
                        'parent1': parent1.id,
                        'parent2': parent2.id,
                        'breakpoint': breakpoint,
                        'score': score
                    }
        
        # Determine if sequence is chimeric based on score threshold
        is_chimeric = best_score > 0.7  # Threshold for chimeric classification
        
        return is_chimeric, best_parents if best_parents else {}
    
    def _calculate_chimeric_score(self, query: str, parent1: str, parent2: str) -> Tuple[float, int]:
        """
        Calculate chimeric score using sliding window approach.
        
        Args:
            query: Query sequence
            parent1: First potential parent
            parent2: Second potential parent
            
        Returns:
            Tuple of (chimeric_score, breakpoint_position)
        """
        if not (len(query) == len(parent1) == len(parent2)):
            # Handle different length sequences by using shortest length
            min_len = min(len(query), len(parent1), len(parent2))
            query = query[:min_len]
            parent1 = parent1[:min_len]
            parent2 = parent2[:min_len]
        
        best_score = 0
        best_breakpoint = 0
        
        # Slide window across sequence
        for breakpoint in range(self.window_size, len(query) - self.window_size, self.step_size):
            # Left part: should match parent1 better than parent2
            left_query = query[:breakpoint]
            left_p1 = parent1[:breakpoint]
            left_p2 = parent2[:breakpoint]
            
            # Right part: should match parent2 better than parent1
            right_query = query[breakpoint:]
            right_p1 = parent1[breakpoint:]
            right_p2 = parent2[breakpoint:]
            
            # Calculate similarities
            left_sim_p1 = self._calculate_similarity(left_query, left_p1)
            left_sim_p2 = self._calculate_similarity(left_query, left_p2)
            right_sim_p1 = self._calculate_similarity(right_query, right_p1)
            right_sim_p2 = self._calculate_similarity(right_query, right_p2)
            
            # Check for chimeric pattern: left matches p1, right matches p2
            if left_sim_p1 > left_sim_p2 and right_sim_p2 > right_sim_p1:
                # Calculate divergence between parents
                parent_divergence = 1 - self._calculate_similarity(parent1, parent2)
                
                if parent_divergence >= self.min_divergence:
                    # Calculate chimeric score
                    left_advantage = left_sim_p1 - left_sim_p2
                    right_advantage = right_sim_p2 - right_sim_p1
                    score = (left_advantage + right_advantage) * parent_divergence
                    
                    if score > best_score:
                        best_score = score
                        best_breakpoint = breakpoint
        
        return best_score, best_breakpoint
    
    def _calculate_similarity(self, seq1: str, seq2: str) -> float:
        """
        Calculate sequence similarity (proportion of matching positions).
        
        Args:
            seq1: First sequence
            seq2: Second sequence
            
        Returns:
            Similarity score (0-1)
        """
        if len(seq1) != len(seq2):
            # Handle different lengths by using minimum length
            min_len = min(len(seq1), len(seq2))
            seq1 = seq1[:min_len]
            seq2 = seq2[:min_len]
        
        if len(seq1) == 0:
            return 0.0
        
        matches = sum(c1 == c2 for c1, c2 in zip(seq1, seq2))
        return matches / len(seq1)
    
    def remove_chimeras_vsearch(self, input_fasta: str, output_fasta: str) -> bool:
        """
        Use VSEARCH for chimera removal (external tool).
        
        Args:
            input_fasta: Input FASTA file
            output_fasta: Output FASTA file (non-chimeric sequences)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import subprocess
            
            cmd = [
                "vsearch",
                "--uchime_denovo", input_fasta,
                "--nonchimeras", output_fasta,
                "--chimeras", output_fasta.replace(".fasta", "_chimeras.fasta")
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"VSEARCH chimera removal completed: {input_fasta} -> {output_fasta}")
                return True
            else:
                logger.error(f"VSEARCH failed: {result.stderr}")
                return False
                
        except FileNotFoundError:
            logger.warning("VSEARCH not found, using internal chimera detection")
            return False
        except Exception as e:
            logger.error(f"VSEARCH chimera removal failed: {e}")
            return False