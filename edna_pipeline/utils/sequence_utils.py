"""Sequence utility functions for common DNA sequence operations."""

from typing import Dict, List, Union
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
import logging

logger = logging.getLogger(__name__)


def reverse_complement(sequence: Union[str, Seq, SeqRecord]) -> str:
    """
    Get reverse complement of DNA sequence.
    
    Args:
        sequence: DNA sequence (string, Seq, or SeqRecord)
        
    Returns:
        Reverse complement as string
    """
    if isinstance(sequence, SeqRecord):
        seq_str = str(sequence.seq)
    elif isinstance(sequence, Seq):
        seq_str = str(sequence)
    else:
        seq_str = str(sequence)
    
    # Convert to uppercase
    seq_str = seq_str.upper()
    
    # Complement mapping
    complement = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C', 'N': 'N'}
    
    # Handle ambiguous nucleotides
    ambiguous = {
        'R': 'Y', 'Y': 'R',  # A/G <-> C/T
        'S': 'S',            # G/C (self-complement)
        'W': 'W',            # A/T (self-complement)
        'K': 'M', 'M': 'K',  # G/T <-> A/C
        'B': 'V', 'V': 'B',  # C/G/T <-> A/C/G
        'D': 'H', 'H': 'D',  # A/G/T <-> A/C/T
    }
    complement.update(ambiguous)
    
    try:
        rev_comp = ''.join(complement.get(base, base) for base in reversed(seq_str))
    except KeyError as e:
        logger.warning(f"Unknown nucleotide in sequence: {e}")
        rev_comp = ''.join(complement.get(base, 'N') for base in reversed(seq_str))
    
    return rev_comp


def translate_dna(sequence: Union[str, Seq, SeqRecord], reading_frame: int = 1,
                  genetic_code: int = 1) -> str:
    """
    Translate DNA sequence to protein.
    
    Args:
        sequence: DNA sequence
        reading_frame: Reading frame (1, 2, or 3)
        genetic_code: Genetic code table (1 = standard)
        
    Returns:
        Amino acid sequence as string
    """
    if isinstance(sequence, SeqRecord):
        dna_seq = sequence.seq
    elif isinstance(sequence, str):
        dna_seq = Seq(sequence)
    else:
        dna_seq = sequence
    
    # Adjust for reading frame
    if reading_frame not in [1, 2, 3]:
        raise ValueError("Reading frame must be 1, 2, or 3")
    
    start_pos = reading_frame - 1
    dna_seq = dna_seq[start_pos:]
    
    try:
        protein_seq = dna_seq.translate(table=genetic_code)
        return str(protein_seq)
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return ""


def gc_content(sequence: Union[str, Seq, SeqRecord]) -> float:
    """
    Calculate GC content of sequence.
    
    Args:
        sequence: DNA sequence
        
    Returns:
        GC content as fraction (0-1)
    """
    if isinstance(sequence, SeqRecord):
        seq_str = str(sequence.seq)
    elif isinstance(sequence, Seq):
        seq_str = str(sequence)
    else:
        seq_str = str(sequence)
    
    seq_str = seq_str.upper()
    
    if len(seq_str) == 0:
        return 0.0
    
    gc_count = seq_str.count('G') + seq_str.count('C')
    return gc_count / len(seq_str)


def at_content(sequence: Union[str, Seq, SeqRecord]) -> float:
    """
    Calculate AT content of sequence.
    
    Args:
        sequence: DNA sequence
        
    Returns:
        AT content as fraction (0-1)
    """
    return 1.0 - gc_content(sequence)


def find_orfs(sequence: Union[str, Seq, SeqRecord], min_length: int = 30,
              genetic_code: int = 1) -> List[Dict]:
    """
    Find open reading frames in DNA sequence.
    
    Args:
        sequence: DNA sequence
        min_length: Minimum ORF length in amino acids
        genetic_code: Genetic code table
        
    Returns:
        List of ORF dictionaries with start, end, frame, and protein sequence
    """
    if isinstance(sequence, SeqRecord):
        dna_seq = str(sequence.seq)
    elif isinstance(sequence, Seq):
        dna_seq = str(sequence)
    else:
        dna_seq = str(sequence)
    
    dna_seq = dna_seq.upper()
    orfs = []
    
    # Start codons
    start_codons = ['ATG']  # Standard start codon
    stop_codons = ['TAA', 'TAG', 'TGA']  # Standard stop codons
    
    # Check all three reading frames
    for frame in range(3):
        frame_seq = dna_seq[frame:]
        
        i = 0
        while i < len(frame_seq) - 2:
            codon = frame_seq[i:i+3]
            
            if codon in start_codons:
                # Found start codon, look for stop codon
                start_pos = frame + i
                
                j = i + 3
                while j < len(frame_seq) - 2:
                    stop_codon = frame_seq[j:j+3]
                    
                    if stop_codon in stop_codons:
                        end_pos = frame + j + 2
                        orf_length = (j - i) // 3  # Length in amino acids
                        
                        if orf_length >= min_length:
                            orf_dna = dna_seq[start_pos:end_pos+1]
                            protein = translate_dna(orf_dna, 1, genetic_code)
                            
                            orfs.append({
                                'start': start_pos,
                                'end': end_pos,
                                'frame': frame + 1,
                                'length_aa': orf_length,
                                'length_nt': end_pos - start_pos + 1,
                                'dna_sequence': orf_dna,
                                'protein_sequence': protein
                            })
                        
                        i = j + 3  # Move past this ORF
                        break
                    
                    j += 3
                else:
                    # No stop codon found
                    i += 3
            else:
                i += 3
    
    return orfs


def find_repeats(sequence: Union[str, Seq, SeqRecord], min_repeat_length: int = 10,
                max_distance: int = 1000) -> List[Dict]:
    """
    Find tandem repeats in DNA sequence.
    
    Args:
        sequence: DNA sequence
        min_repeat_length: Minimum length of repeat unit
        max_distance: Maximum distance to search for repeats
        
    Returns:
        List of repeat dictionaries
    """
    if isinstance(sequence, SeqRecord):
        seq_str = str(sequence.seq)
    elif isinstance(sequence, Seq):
        seq_str = str(sequence)
    else:
        seq_str = str(sequence)
    
    seq_str = seq_str.upper()
    repeats = []
    
    # Simple tandem repeat finder
    for start in range(len(seq_str)):
        for repeat_len in range(min_repeat_length, min(100, len(seq_str) - start)):
            repeat_unit = seq_str[start:start + repeat_len]
            
            # Count consecutive repeats
            pos = start + repeat_len
            repeat_count = 1
            
            while pos + repeat_len <= len(seq_str):
                next_unit = seq_str[pos:pos + repeat_len]
                if next_unit == repeat_unit:
                    repeat_count += 1
                    pos += repeat_len
                else:
                    break
            
            # Only report if we found multiple repeats
            if repeat_count >= 2:
                total_length = repeat_count * repeat_len
                
                repeats.append({
                    'start': start,
                    'end': start + total_length - 1,
                    'repeat_unit': repeat_unit,
                    'repeat_length': repeat_len,
                    'repeat_count': repeat_count,
                    'total_length': total_length
                })
    
    # Remove overlapping repeats (keep longest)
    filtered_repeats = []
    repeats.sort(key=lambda x: x['total_length'], reverse=True)
    
    for repeat in repeats:
        overlap = False
        for existing in filtered_repeats:
            if (repeat['start'] < existing['end'] and repeat['end'] > existing['start']):
                overlap = True
                break
        
        if not overlap:
            filtered_repeats.append(repeat)
    
    return filtered_repeats


def calculate_sequence_complexity(sequence: Union[str, Seq, SeqRecord]) -> float:
    """
    Calculate sequence complexity using Trifonov's method.
    
    Args:
        sequence: DNA sequence
        
    Returns:
        Complexity score (0-1, higher = more complex)
    """
    if isinstance(sequence, SeqRecord):
        seq_str = str(sequence.seq)
    elif isinstance(sequence, Seq):
        seq_str = str(sequence)
    else:
        seq_str = str(sequence)
    
    seq_str = seq_str.upper()
    
    if len(seq_str) == 0:
        return 0.0
    
    # Count different types of subsequences
    subsequence_counts = {}
    
    # Check subsequences of different lengths
    for subseq_len in range(1, min(10, len(seq_str) + 1)):
        unique_subseqs = set()
        
        for i in range(len(seq_str) - subseq_len + 1):
            subseq = seq_str[i:i + subseq_len]
            unique_subseqs.add(subseq)
        
        # Calculate relative complexity for this subsequence length
        max_possible = min(4 ** subseq_len, len(seq_str) - subseq_len + 1)
        if max_possible > 0:
            complexity = len(unique_subseqs) / max_possible
            subsequence_counts[subseq_len] = complexity
    
    # Average complexity across all subsequence lengths
    if subsequence_counts:
        return sum(subsequence_counts.values()) / len(subsequence_counts)
    else:
        return 0.0


def mask_low_complexity(sequence: Union[str, Seq, SeqRecord], 
                       complexity_threshold: float = 0.3, 
                       window_size: int = 20) -> str:
    """
    Mask low-complexity regions in sequence.
    
    Args:
        sequence: DNA sequence
        complexity_threshold: Threshold below which to mask
        window_size: Size of sliding window
        
    Returns:
        Masked sequence with N's in low-complexity regions
    """
    if isinstance(sequence, SeqRecord):
        seq_str = str(sequence.seq)
    elif isinstance(sequence, Seq):
        seq_str = str(sequence)
    else:
        seq_str = str(sequence)
    
    seq_str = seq_str.upper()
    masked_seq = list(seq_str)
    
    # Sliding window complexity analysis
    for i in range(len(seq_str) - window_size + 1):
        window = seq_str[i:i + window_size]
        complexity = calculate_sequence_complexity(window)
        
        if complexity < complexity_threshold:
            # Mask this window
            for j in range(i, i + window_size):
                masked_seq[j] = 'N'
    
    return ''.join(masked_seq)


def validate_dna_sequence(sequence: Union[str, Seq, SeqRecord]) -> Dict[str, any]:
    """
    Validate DNA sequence and return quality metrics.
    
    Args:
        sequence: DNA sequence
        
    Returns:
        Dictionary with validation results
    """
    if isinstance(sequence, SeqRecord):
        seq_str = str(sequence.seq)
    elif isinstance(sequence, Seq):
        seq_str = str(sequence)
    else:
        seq_str = str(sequence)
    
    seq_str = seq_str.upper()
    
    # Count different nucleotides
    nucleotide_counts = {
        'A': seq_str.count('A'),
        'C': seq_str.count('C'),
        'G': seq_str.count('G'),
        'T': seq_str.count('T'),
        'N': seq_str.count('N')
    }
    
    # Count ambiguous bases
    ambiguous_bases = 'RYSWKMBDHV'
    ambiguous_count = sum(seq_str.count(base) for base in ambiguous_bases)
    
    # Count invalid characters
    valid_bases = set('ACGTNRYSWKMBDHV')
    invalid_chars = [c for c in seq_str if c not in valid_bases]
    
    total_length = len(seq_str)
    valid_length = total_length - len(invalid_chars)
    
    validation = {
        'length': total_length,
        'valid_length': valid_length,
        'nucleotide_counts': nucleotide_counts,
        'gc_content': gc_content(seq_str) if total_length > 0 else 0.0,
        'ambiguous_bases': ambiguous_count,
        'invalid_characters': invalid_chars,
        'n_content': nucleotide_counts['N'] / total_length if total_length > 0 else 0.0,
        'is_valid': len(invalid_chars) == 0,
        'quality_score': valid_length / total_length if total_length > 0 else 0.0
    }
    
    return validation