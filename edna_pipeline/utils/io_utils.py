"""I/O utility functions for sequence file handling."""

import gzip
from typing import List, Iterator, Union
from pathlib import Path
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
import logging

logger = logging.getLogger(__name__)


def read_fastq(filepath: Union[str, Path], compressed: bool = None) -> List[SeqRecord]:
    """
    Read sequences from a FASTQ file.
    
    Args:
        filepath: Path to FASTQ file
        compressed: Whether file is gzip compressed. Auto-detected if None.
        
    Returns:
        List of sequence records
    """
    filepath = Path(filepath)
    
    if compressed is None:
        compressed = filepath.suffix.lower() == '.gz'
    
    try:
        if compressed:
            with gzip.open(filepath, 'rt') as handle:
                sequences = list(SeqIO.parse(handle, 'fastq'))
        else:
            with open(filepath, 'r') as handle:
                sequences = list(SeqIO.parse(handle, 'fastq'))
        
        logger.info(f"Read {len(sequences)} sequences from {filepath}")
        return sequences
        
    except Exception as e:
        logger.error(f"Error reading FASTQ file {filepath}: {e}")
        raise


def write_fastq(sequences: List[SeqRecord], filepath: Union[str, Path], 
                compressed: bool = None) -> None:
    """
    Write sequences to a FASTQ file.
    
    Args:
        sequences: List of sequence records
        filepath: Output file path
        compressed: Whether to compress output. Auto-detected if None.
    """
    filepath = Path(filepath)
    
    if compressed is None:
        compressed = filepath.suffix.lower() == '.gz'
    
    try:
        if compressed:
            with gzip.open(filepath, 'wt') as handle:
                SeqIO.write(sequences, handle, 'fastq')
        else:
            with open(filepath, 'w') as handle:
                SeqIO.write(sequences, handle, 'fastq')
        
        logger.info(f"Wrote {len(sequences)} sequences to {filepath}")
        
    except Exception as e:
        logger.error(f"Error writing FASTQ file {filepath}: {e}")
        raise


def read_fasta(filepath: Union[str, Path], compressed: bool = None) -> List[SeqRecord]:
    """
    Read sequences from a FASTA file.
    
    Args:
        filepath: Path to FASTA file
        compressed: Whether file is gzip compressed. Auto-detected if None.
        
    Returns:
        List of sequence records
    """
    filepath = Path(filepath)
    
    if compressed is None:
        compressed = filepath.suffix.lower() == '.gz'
    
    try:
        if compressed:
            with gzip.open(filepath, 'rt') as handle:
                sequences = list(SeqIO.parse(handle, 'fasta'))
        else:
            with open(filepath, 'r') as handle:
                sequences = list(SeqIO.parse(handle, 'fasta'))
        
        logger.info(f"Read {len(sequences)} sequences from {filepath}")
        return sequences
        
    except Exception as e:
        logger.error(f"Error reading FASTA file {filepath}: {e}")
        raise


def write_fasta(sequences: List[SeqRecord], filepath: Union[str, Path], 
                compressed: bool = None) -> None:
    """
    Write sequences to a FASTA file.
    
    Args:
        sequences: List of sequence records
        filepath: Output file path
        compressed: Whether to compress output. Auto-detected if None.
    """
    filepath = Path(filepath)
    
    if compressed is None:
        compressed = filepath.suffix.lower() == '.gz'
    
    try:
        if compressed:
            with gzip.open(filepath, 'wt') as handle:
                SeqIO.write(sequences, handle, 'fasta')
        else:
            with open(filepath, 'w') as handle:
                SeqIO.write(sequences, handle, 'fasta')
        
        logger.info(f"Wrote {len(sequences)} sequences to {filepath}")
        
    except Exception as e:
        logger.error(f"Error writing FASTA file {filepath}: {e}")
        raise


def read_sequences_iter(filepath: Union[str, Path], format: str = 'fastq', 
                       compressed: bool = None) -> Iterator[SeqRecord]:
    """
    Read sequences from file as an iterator (memory efficient for large files).
    
    Args:
        filepath: Path to sequence file
        format: File format ('fastq' or 'fasta')
        compressed: Whether file is gzip compressed. Auto-detected if None.
        
    Yields:
        Sequence records
    """
    filepath = Path(filepath)
    
    if compressed is None:
        compressed = filepath.suffix.lower() == '.gz'
    
    try:
        if compressed:
            with gzip.open(filepath, 'rt') as handle:
                for record in SeqIO.parse(handle, format):
                    yield record
        else:
            with open(filepath, 'r') as handle:
                for record in SeqIO.parse(handle, format):
                    yield record
                    
    except Exception as e:
        logger.error(f"Error reading file {filepath}: {e}")
        raise