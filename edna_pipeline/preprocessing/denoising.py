"""Denoising algorithms for eDNA sequence analysis."""

import os
import csv
import sys
import shutil
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union, Any
from abc import ABC, abstractmethod
from collections import Counter

# Keep Bio imports for other algorithms like DenoiseDeblur if they exist
from Bio.SeqRecord import SeqRecord
from Bio.Seq import Seq
import numpy as np

logger = logging.getLogger(__name__)

USER_R_SCRIPT = """\
library(dada2)
args <- commandArgs(trailingOnly=TRUE)
input_fastq <- args[1]
output_dir  <- args[2]

# Learn error model
err <- learnErrors(input_fastq, multithread=TRUE)

# Dereplicate
derep <- derepFastq(input_fastq)

# DADA2 inference
dada_result <- dada(derep, err=err, multithread=TRUE)

# Make sequence table
seqtab <- makeSequenceTable(dada_result)

# Remove chimeras
seqtab_nochim <- removeBimeraDenovo(seqtab, method="consensus",
                                     multithread=TRUE)

# Write outputs
asvs <- colnames(seqtab_nochim)
counts <- as.vector(seqtab_nochim)
writeXStringSet(DNAStringSet(asvs),
                filepath=file.path(output_dir, "asvs.fasta"))
write.csv(data.frame(asv=asvs, count=counts),
          file.path(output_dir, "abundance.csv"), row.names=FALSE)
"""


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
    def denoise(self, input_data: Any) -> Any:
        """
        Denoise sequences to generate ASVs.
        
        Args:
            input_data: Input sequences or file path
            
        Returns:
            Denoising results
        """
        pass


class DenoiseDADA2(DenoiseBase):
    """
    Industry-standard DADA2/UNOISE3 denoising implementation.
    
    This replaces the naive Hamming-distance OTU clustering with a true ASV algorithm.
    By default, it uses VSEARCH UNOISE3 for fast CLI-based inference, falling back
    to an Rscript running the actual DADA2 package if required.
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.unoise_alpha = config.get("unoise_alpha", 2.0)
        self.min_size = config.get("min_size", 2)
        self.min_unique_size = config.get("min_unique_size", 2)
        self.threads = config.get("threads", os.cpu_count() or 1)
        self.use_dada2_fallback = config.get("use_dada2_fallback", True)
        self.stats = {}

    def denoise(self, input_fasta_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Denoise the input FASTA file using VSEARCH UNOISE3 or DADA2 fallback.
        
        Args:
            input_fasta_path: Path to the input FASTA/FASTQ file.
        
        Returns:
            Dictionary containing paths to output and stats:
                asv_fasta_path: Path
                abundance_table: dict
                stats: dict
                method_used: "unoise3" | "dada2"
        """
        input_fasta_path = Path(input_fasta_path).resolve()
        
        # Determine total input sequences (bioinformatic rationale: needed for tracking read loss)
        input_reads = self._count_fasta_records(input_fasta_path)
        self.stats["input_sequences"] = input_reads
        
        output_dir = input_fasta_path.parent / f"denoised_{input_fasta_path.stem}"
        output_dir.mkdir(parents=True, exist_ok=True)
        final_asv_fasta = output_dir / "asvs_final.fasta"
        
        has_vsearch = shutil.which("vsearch") is not None
        
        if has_vsearch:
            method_used = "unoise3"
            asv_fasta, abundance_tsv = self._run_vsearch_pipeline(input_fasta_path, output_dir)
            abundance_dict = self._parse_vsearch_abundance(abundance_tsv)
        else:
            if not self.use_dada2_fallback:
                raise RuntimeError("VSEARCH is not installed and DADA2 fallback is disabled.")
            has_rscript = shutil.which("Rscript") is not None
            if not has_rscript:
                raise RuntimeError(
                    "Neither 'vsearch' nor 'Rscript' found strictly in PATH. "
                    "Please install either vsearch (e.g. 'conda install -c bioconda vsearch') "
                    "or R with the dada2 package."
                )
            method_used = "dada2"
            asv_fasta, abundance_csv = self._run_dada2_pipeline(input_fasta_path, output_dir)
            abundance_dict = self._parse_dada2_abundance(abundance_csv)
            
        # Format ASVs and sort by abundance (needed by downstream applications like taxonomic assignment)
        formatted_abundance = self._format_and_write_asvs(abundance_dict, final_asv_fasta)
        
        # Calculate final sequence statistics and chimera rates based on pipeline output
        self.stats["asvs_after_chimera"] = len(formatted_abundance)
        if "asvs_before_chimera" in self.stats and self.stats["asvs_before_chimera"] > 0:
            chimeras_removed = self.stats["asvs_before_chimera"] - self.stats["asvs_after_chimera"]
            self.stats["chimera_rate"] = (chimeras_removed / self.stats["asvs_before_chimera"]) * 100.0
        else:
            self.stats["chimera_rate"] = 0.0
            
        return {
            "asv_fasta_path": final_asv_fasta,
            "abundance_table": formatted_abundance,
            "stats": self.stats,
            "method_used": method_used
        }

    def _count_fasta_records(self, fasta_path: Path) -> int:
        """Count the number of sequences in a FASTA/FASTQ file without loading entirely into memory."""
        count = 0
        with open(fasta_path, "r") as f:
            for line in f:
                if line.startswith(">"):
                    count += 1
        return count

    def _run_vsearch_pipeline(self, input_fasta: Path, output_dir: Path) -> Tuple[Path, Path]:
        """
        Run the VSEARCH UNOISE3 pipeline.
        
        Steps:
        1. Dereplication (--derep_fulllength): Removes identical duplicate sequences, outputting unique counts.
        2. UNOISE3 Clustering (--cluster_unoise): Clusters the dereplicated sequences, effectively removing sequencing errors 
           while maintaining single-nucleotide resolution to discover actual ASVs.
        3. Chimera removal (--uchime3_denovo): Removes bipartite artificially combined sequences formed during PCR.
        4. Read mapping for abundance (--usearch_global): Maps all original reads back against final ASVs.
        """
        logger.info("Running VSEARCH UNOISE3 denoising pipeline...")
        
        # Step 1: Dereplication
        derep_fasta = output_dir / "derep.fasta"
        derep_uc = output_dir / "derep.uc"
        
        cmd1 = [
            "vsearch", "--derep_fulllength", str(input_fasta),
            "--output", str(derep_fasta),
            "--sizeout",
            "--minuniquesize", str(self.min_unique_size),
            "--uc", str(derep_uc)
        ]
        self._run_cmd(cmd1, "Dereplication")
        self.stats["unique_sequences"] = self._count_fasta_records(derep_fasta)
        
        # Step 2: UNOISE3
        denoised_fasta = output_dir / "denoised.fasta"
        cmd2 = [
            "vsearch", "--cluster_unoise", str(derep_fasta),
            "--centroids", str(denoised_fasta),
            "--sizein", "--sizeout",
            "--minsize", str(self.min_size),
            "--unoise_alpha", str(self.unoise_alpha)
        ]
        self._run_cmd(cmd2, "UNOISE3 clustering")
        self.stats["asvs_before_chimera"] = self._count_fasta_records(denoised_fasta)
        
        # Step 3: Chimera removal
        asvs_fasta = output_dir / "asvs.fasta"
        cmd3 = [
            "vsearch", "--uchime3_denovo", str(denoised_fasta),
            "--nonchimeras", str(asvs_fasta),
            "--sizein", "--sizeout"
        ]
        self._run_cmd(cmd3, "Chimera removal")
        
        # Step 4: Map reads to get abundance table
        abundance_tsv = output_dir / "abundance_table.tsv"
        cmd4 = [
            "vsearch", "--usearch_global", str(input_fasta),
            "--db", str(asvs_fasta),
            "--id", "0.97",
            "--otutabout", str(abundance_tsv),
            "--sizein"
        ]
        self._run_cmd(cmd4, "Read mapping")
        
        return asvs_fasta, abundance_tsv

    def _run_dada2_pipeline(self, input_fastq: Path, output_dir: Path) -> Tuple[Path, Path]:
        """
        Run the DADA2 pipeline via embedded Rscript as a fallback.
        The external R script learns a parametric error model specific to the sequencing
        platform characteristics directly from the data avoiding predefined models.
        """
        logger.info("Running DADA2 fallback via Rscript...")
        
        rscript_path = output_dir / "run_dada2.R"
        with open(rscript_path, "w") as f:
            f.write(USER_R_SCRIPT)
            
        cmd = ["Rscript", str(rscript_path), str(input_fastq), str(output_dir)]
        self._run_cmd(cmd, "DADA2 R script execution")
        
        asvs_fasta = output_dir / "asvs.fasta"
        abundance_csv = output_dir / "abundance.csv"
        
        if asvs_fasta.exists():
            self.stats["asvs_before_chimera"] = self._count_fasta_records(asvs_fasta)
        
        return asvs_fasta, abundance_csv

    def _run_cmd(self, cmd: List[str], step_name: str):
        """Helper to run a subprocess command with error handling tracking output internally."""
        try:
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.debug(f"{step_name} completed.")
        except subprocess.CalledProcessError as e:
            logger.error(f"{step_name} failed with exit code {e.returncode}")
            logger.error(f"Stderr: {e.stderr}")
            raise RuntimeError(f"{step_name} failed: {e.stderr}") from e

    def _parse_vsearch_abundance(self, abundance_tsv: Path) -> Dict[str, int]:
        """
        Parse VSEARCH OTU table into a {seq_id: abundance} dictionary.
        """
        raw_abundances = {}
        with open(abundance_tsv, "r") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if not row or row[0].startswith("#"):
                    continue
                seq_id = row[0]
                count = sum(int(float(x)) for x in row[1:] if x.strip())
                raw_abundances[seq_id] = count
        return raw_abundances

    def _parse_dada2_abundance(self, abundance_csv: Path) -> Dict[str, int]:
        """
        Parse DADA2 CSV generated by R script into a {sequence: abundance} dictionary.
        """
        raw_abundances = {}
        with open(abundance_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                seq = row["asv"]
                count = int(float(row["count"]))
                raw_abundances[seq] = count
        return raw_abundances

    def _format_and_write_asvs(self, raw_abundances: Dict[str, int], final_fasta: Path) -> Dict[str, Dict[str, Any]]:
        """
        Match abundances to sequences, assign zero-padded ASV IDs (sorted by abundance),
        write out the final FASTA per requirements, and return the required dictionary format.
        """
        seq_to_count = {}
        output_dir = final_fasta.parent
        asvs_fasta = output_dir / "asvs.fasta"
        
        # Check if dictionary keys natively look like sequences (DADA2 fallback logic)
        sample_key = next(iter(raw_abundances.keys())) if raw_abundances else ""
        if sample_key and set(sample_key).issubset(set("ACGTNacgtn")):
            seq_to_count = raw_abundances
        else:
            # Keys are IDs from VSEARCH, we need to extract their actual sequences
            id_to_seq = {}
            current_id = None
            current_seq = []
            
            if asvs_fasta.exists():
                with open(asvs_fasta, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith(">"):
                            if current_id:
                                id_to_seq[current_id] = "".join(current_seq)
                            current_id = line[1:].split(";")[0]
                            current_seq = []
                        else:
                            current_seq.append(line)
                    if current_id:
                         id_to_seq[current_id] = "".join(current_seq)
            
            for seq_id, count in raw_abundances.items():
                clean_id = seq_id.split(";")[0]
                if clean_id in id_to_seq:
                    seq_to_count[id_to_seq[clean_id]] = count
        
        # Sort by abundance descending
        sorted_seqs = sorted(seq_to_count.items(), key=lambda x: x[1], reverse=True)
        
        final_dict = {}
        with open(final_fasta, "w") as f_out:
            for idx, (seq, count) in enumerate(sorted_seqs, 1):
                asv_id = f"ASV_{idx:04d}"
                # Requested plain format: >ASV_0001;size=1532
                f_out.write(f">{asv_id};size={count}\\n{seq}\\n")
                final_dict[asv_id] = {
                    "sequence": seq,
                    "abundance": count
                }
                
        return final_dict


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