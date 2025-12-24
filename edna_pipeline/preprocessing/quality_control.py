"""Quality control functions for eDNA sequence preprocessing."""

import os
import subprocess
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path
import logging
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
import numpy as np
from ..utils.io_utils import read_fastq, write_fastq

logger = logging.getLogger(__name__)


class QualityController:
    """Quality control and filtering for sequencing reads."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize quality controller.
        
        Args:
            config: Configuration dictionary with quality control parameters
        """
        self.config = config
        self.quality_threshold = config.get("quality_threshold", 20)
        self.min_length = config.get("min_length", 100)
        self.max_length = config.get("max_length", 2000)
        self.max_expected_errors = config.get("max_expected_errors", 2)
        self.trim_primers = config.get("trim_primers", True)
        
        # Common primer sequences for 18S and COI
        self.primers = {
            "18S_F": "CCAGCASCYGCGGTAATTCC",
            "18S_R": "ACTTTCGTTCTTGATYRA",
            "COI_F": "GGWACWGGWTGAACWGTWTAYCCYCC",
            "COI_R": "TAIACYTCIGGRTGICCRAARAAYCA"
        }
    
    def filter_by_quality(self, sequences: List[SeqRecord]) -> List[SeqRecord]:
        """
        Filter sequences based on quality scores.
        
        Args:
            sequences: List of sequence records with quality scores
            
        Returns:
            Filtered sequences
        """
        filtered = []
        
        for seq in sequences:
            if not hasattr(seq, 'letter_annotations') or 'phred_quality' not in seq.letter_annotations:
                # If no quality scores available, keep sequence
                filtered.append(seq)
                continue
            
            quality_scores = seq.letter_annotations['phred_quality']
            mean_quality = np.mean(quality_scores)
            
            # Calculate expected errors
            error_probs = [10**(-q/10) for q in quality_scores]
            expected_errors = sum(error_probs)
            
            if (mean_quality >= self.quality_threshold and 
                expected_errors <= self.max_expected_errors):
                filtered.append(seq)
        
        logger.info(f"Quality filtering: {len(filtered)}/{len(sequences)} sequences passed")
        return filtered
    
    def filter_by_length(self, sequences: List[SeqRecord]) -> List[SeqRecord]:
        """
        Filter sequences based on length.
        
        Args:
            sequences: List of sequence records
            
        Returns:
            Length-filtered sequences
        """
        filtered = [
            seq for seq in sequences 
            if self.min_length <= len(seq.seq) <= self.max_length
        ]
        
        logger.info(f"Length filtering: {len(filtered)}/{len(sequences)} sequences passed")
        return filtered
    
    def trim_primers_cutadapt(self, input_fastq: str, output_fastq: str,
                             forward_primer: str = None, reverse_primer: str = None) -> bool:
        """
        Trim primers using cutadapt.
        
        Args:
            input_fastq: Input FASTQ file path
            output_fastq: Output FASTQ file path
            forward_primer: Forward primer sequence
            reverse_primer: Reverse primer sequence
            
        Returns:
            True if successful, False otherwise
        """
        if not self.trim_primers:
            return True
        
        try:
            cmd = ["cutadapt"]
            
            # Add primer sequences
            if forward_primer:
                cmd.extend(["-g", forward_primer])
            if reverse_primer:
                cmd.extend(["-a", reverse_primer])
            
            # Add quality and length filtering
            cmd.extend([
                "-q", str(self.quality_threshold),
                "-m", str(self.min_length),
                "-M", str(self.max_length),
                "--max-expected-errors", str(self.max_expected_errors),
                "-o", output_fastq,
                input_fastq
            ])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Successfully trimmed primers: {input_fastq} -> {output_fastq}")
                return True
            else:
                logger.error(f"Cutadapt failed: {result.stderr}")
                return False
                
        except FileNotFoundError:
            logger.warning("Cutadapt not found, using internal primer trimming")
            return self._trim_primers_internal(input_fastq, output_fastq, 
                                             forward_primer, reverse_primer)
    
    def _trim_primers_internal(self, input_fastq: str, output_fastq: str,
                              forward_primer: str = None, reverse_primer: str = None) -> bool:
        """
        Internal primer trimming implementation.
        
        Args:
            input_fastq: Input FASTQ file path
            output_fastq: Output FASTQ file path
            forward_primer: Forward primer sequence
            reverse_primer: Reverse primer sequence
            
        Returns:
            True if successful, False otherwise
        """
        try:
            sequences = read_fastq(input_fastq)
            trimmed_sequences = []
            
            for seq in sequences:
                seq_str = str(seq.seq)
                start_pos = 0
                end_pos = len(seq_str)
                
                # Find and remove forward primer
                if forward_primer:
                    primer_pos = seq_str.find(forward_primer)
                    if primer_pos != -1:
                        start_pos = primer_pos + len(forward_primer)
                
                # Find and remove reverse primer
                if reverse_primer:
                    # Look for reverse complement
                    from Bio.Seq import Seq
                    rev_primer = str(Seq(reverse_primer).reverse_complement())
                    primer_pos = seq_str.find(rev_primer)
                    if primer_pos != -1:
                        end_pos = primer_pos
                
                # Extract trimmed sequence
                if start_pos < end_pos:
                    trimmed_seq = seq[start_pos:end_pos]
                    if len(trimmed_seq) >= self.min_length:
                        trimmed_sequences.append(trimmed_seq)
            
            write_fastq(trimmed_sequences, output_fastq)
            logger.info(f"Internal primer trimming: {len(trimmed_sequences)} sequences processed")
            return True
            
        except Exception as e:
            logger.error(f"Internal primer trimming failed: {e}")
            return False
    
    def remove_ambiguous_bases(self, sequences: List[SeqRecord], 
                              max_ambiguous: int = 0) -> List[SeqRecord]:
        """
        Remove sequences with too many ambiguous bases (N, R, Y, etc.).
        
        Args:
            sequences: List of sequence records
            max_ambiguous: Maximum number of ambiguous bases allowed
            
        Returns:
            Filtered sequences
        """
        filtered = []
        ambiguous_bases = set('NRYSWKMDHVB')
        
        for seq in sequences:
            seq_str = str(seq.seq).upper()
            ambiguous_count = sum(1 for base in seq_str if base in ambiguous_bases)
            
            if ambiguous_count <= max_ambiguous:
                filtered.append(seq)
        
        logger.info(f"Ambiguous base filtering: {len(filtered)}/{len(sequences)} sequences passed")
        return filtered
    
    def process_paired_reads(self, forward_file: str, reverse_file: str,
                           output_dir: str) -> Tuple[str, str]:
        """
        Process paired-end reads.
        
        Args:
            forward_file: Forward reads FASTQ file
            reverse_file: Reverse reads FASTQ file
            output_dir: Output directory
            
        Returns:
            Tuple of (filtered_forward_file, filtered_reverse_file)
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Output file paths
        forward_out = os.path.join(output_dir, "filtered_R1.fastq")
        reverse_out = os.path.join(output_dir, "filtered_R2.fastq")
        
        # Process forward reads
        if self.trim_primers:
            self.trim_primers_cutadapt(
                forward_file, forward_out,
                forward_primer=self.primers.get("18S_F"),
                reverse_primer=None
            )
        else:
            # Just quality filter
            sequences = read_fastq(forward_file)
            sequences = self.filter_by_quality(sequences)
            sequences = self.filter_by_length(sequences)
            sequences = self.remove_ambiguous_bases(sequences)
            write_fastq(sequences, forward_out)
        
        # Process reverse reads
        if self.trim_primers:
            self.trim_primers_cutadapt(
                reverse_file, reverse_out,
                forward_primer=None,
                reverse_primer=self.primers.get("18S_R")
            )
        else:
            # Just quality filter
            sequences = read_fastq(reverse_file)
            sequences = self.filter_by_quality(sequences)
            sequences = self.filter_by_length(sequences)
            sequences = self.remove_ambiguous_bases(sequences)
            write_fastq(sequences, reverse_out)
        
        return forward_out, reverse_out
    
    def get_quality_stats(self, fastq_file: str) -> Dict[str, Any]:
        """
        Get quality statistics for a FASTQ file.
        
        Args:
            fastq_file: FASTQ file path
            
        Returns:
            Dictionary with quality statistics
        """
        sequences = read_fastq(fastq_file)
        
        lengths = [len(seq.seq) for seq in sequences]
        quality_scores = []
        
        for seq in sequences:
            if hasattr(seq, 'letter_annotations') and 'phred_quality' in seq.letter_annotations:
                quality_scores.extend(seq.letter_annotations['phred_quality'])
        
        stats = {
            "total_sequences": len(sequences),
            "mean_length": np.mean(lengths) if lengths else 0,
            "std_length": np.std(lengths) if lengths else 0,
            "min_length": min(lengths) if lengths else 0,
            "max_length": max(lengths) if lengths else 0,
            "mean_quality": np.mean(quality_scores) if quality_scores else 0,
            "std_quality": np.std(quality_scores) if quality_scores else 0
        }
        
        return stats