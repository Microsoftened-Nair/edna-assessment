"""Main sequence preprocessor integrating all preprocessing steps."""

import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Dict, Tuple, Any, Optional
from pathlib import Path
from Bio.SeqRecord import SeqRecord
import logging

from .quality_control import QualityController
from .denoising import DenoiseDADA2, DenoiseDeblur
from .chimera_removal import ChimeraRemover
from ..utils.io_utils import read_fastq, write_fastq, read_fasta, write_fasta

logger = logging.getLogger(__name__)


class SequencePreprocessor:
    """Main sequence preprocessing pipeline."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize sequence preprocessor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.preprocessing_config = config.get("preprocessing", {})
        
        # Initialize components
        self.quality_controller = QualityController(self.preprocessing_config)
        
        # Initialize denoiser based on config
        denoise_method = self.preprocessing_config.get("denoise_method", "dada2")
        if denoise_method.lower() == "dada2":
            self.denoiser = DenoiseDADA2(self.preprocessing_config)
        elif denoise_method.lower() == "deblur":
            self.denoiser = DenoiseDeblur(self.preprocessing_config)
        else:
            raise ValueError(f"Unknown denoise method: {denoise_method}")
        
        self.chimera_remover = ChimeraRemover(self.preprocessing_config)
        
        # Processing flags
        self.remove_chimeras = self.preprocessing_config.get("remove_chimeras", True)
        self.stats: Dict[str, Any] = {}
        
    def process_single_end_reads(self, input_file: str, output_dir: str,
                               sample_id: str = None) -> Dict[str, Any]:
        """
        Process single-end reads through the complete preprocessing pipeline.
        
        Args:
            input_file: Input FASTQ file
            output_dir: Output directory for results
            sample_id: Sample identifier (if None, derived from filename)
            
        Returns:
            Dictionary with processing results and file paths
        """
        if sample_id is None:
            sample_id = Path(input_file).stem
        
        logger.info(f"Starting preprocessing of single-end reads: {sample_id}")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        sample_dir = os.path.join(output_dir, sample_id)
        os.makedirs(sample_dir, exist_ok=True)
        
        results = {
            "sample_id": sample_id,
            "input_file": input_file,
            "output_dir": sample_dir,
            "processing_steps": []
        }
        
        try:
            # Step 1: Quality filtering and trimming
            logger.info("Step 1: Quality control and filtering")
            filtered_file = os.path.join(sample_dir, "filtered.fastq")
            
            # Read input sequences
            sequences = read_fastq(input_file)
            initial_count = len(sequences)
            
            # Apply quality filtering
            sequences = self.quality_controller.filter_by_quality(sequences)
            sequences = self.quality_controller.filter_by_length(sequences)
            sequences = self.quality_controller.remove_ambiguous_bases(sequences)
            
            # Write filtered sequences
            write_fastq(sequences, filtered_file)
            
            qc_stats = {
                "step": "quality_control",
                "input_sequences": initial_count,
                "output_sequences": len(sequences),
                "output_file": filtered_file
            }
            results["processing_steps"].append(qc_stats)
            
            # Step 2: Denoising (ASV generation)
            logger.info("Step 2: Denoising and ASV generation")
            asvs, abundance_table = self.denoiser.denoise(sequences)
            
            # Save ASVs
            asv_file = os.path.join(sample_dir, "asvs.fasta")
            write_fasta(asvs, asv_file)
            
            denoise_stats = {
                "step": "denoising",
                "method": type(self.denoiser).__name__,
                "input_sequences": len(sequences),
                "output_asvs": len(asvs),
                "output_file": asv_file,
                "abundance_table": abundance_table
            }
            results["processing_steps"].append(denoise_stats)
            
            # Step 3: Chimera removal (optional)
            if self.remove_chimeras:
                logger.info("Step 3: Chimera detection and removal")
                clean_asvs, chimeric_ids = self.chimera_remover.remove_chimeras(
                    asvs, abundance_table
                )
                
                # Save clean ASVs
                clean_asv_file = os.path.join(sample_dir, "asvs_no_chimeras.fasta")
                write_fasta(clean_asvs, clean_asv_file)
                
                # Update abundance table
                clean_abundance_table = {
                    asv_id: count for asv_id, count in abundance_table.items()
                    if asv_id not in chimeric_ids
                }
                
                chimera_stats = {
                    "step": "chimera_removal",
                    "input_asvs": len(asvs),
                    "output_asvs": len(clean_asvs),
                    "chimeric_asvs": len(chimeric_ids),
                    "output_file": clean_asv_file,
                    "abundance_table": clean_abundance_table
                }
                results["processing_steps"].append(chimera_stats)
                
                # Use clean data for final output
                final_asvs = clean_asvs
                final_abundance_table = clean_abundance_table
                final_asv_file = clean_asv_file
            else:
                final_asvs = asvs
                final_abundance_table = abundance_table
                final_asv_file = asv_file
            
            # Save final results
            results.update({
                "final_asvs": len(final_asvs),
                "final_asv_file": final_asv_file,
                "abundance_table": final_abundance_table,
                "success": True
            })
            
            # Save abundance table to file
            abundance_file = os.path.join(sample_dir, "abundance_table.txt")
            self._save_abundance_table(final_abundance_table, abundance_file)
            results["abundance_file"] = abundance_file
            
            # Generate summary statistics
            summary_stats = self._generate_summary_stats(results)
            results["summary_stats"] = summary_stats
            
            # Save processing log
            log_file = os.path.join(sample_dir, "preprocessing_log.txt")
            self._save_processing_log(results, log_file)
            results["log_file"] = log_file
            
            logger.info(f"Preprocessing completed successfully for {sample_id}")
            logger.info(f"Final output: {len(final_asvs)} ASVs")
            
        except Exception as e:
            logger.error(f"Preprocessing failed for {sample_id}: {str(e)}")
            results["success"] = False
            results["error"] = str(e)
            raise
        
        return results

    def process_paired_end_reads(self, forward_file: str, reverse_file: str,
                                 output_dir: str, sample_id: str = None) -> Dict[str, Any]:
        """Process paired-end reads through the preprocessing pipeline."""
        if sample_id is None:
            sample_id = Path(forward_file).stem.replace("_R1", "").replace("_1", "")

        logger.info(f"Starting preprocessing of paired-end reads: {sample_id}")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        sample_dir = output_path / sample_id
        sample_dir.mkdir(parents=True, exist_ok=True)
        temp_merge_dir = Path(tempfile.mkdtemp(prefix=f"merge_{sample_id}_"))
        cleanup_temp_dir = False

        # Reset per-sample merge stats so callers can inspect deterministic values.
        self.stats["merged_reads"] = 0
        self.stats["merge_rate"] = 0.0

        results: Dict[str, Any] = {
            "sample_id": sample_id,
            "input_files": {
                "forward": forward_file,
                "reverse": reverse_file
            },
            "output_dir": str(sample_dir),
            "processing_steps": []
        }

        try:
            logger.info("Step 1: Quality control for paired-end reads")
            forward_raw = read_fastq(forward_file)
            reverse_raw = read_fastq(reverse_file)

            filtered_forward_path, filtered_reverse_path = self.quality_controller.process_paired_reads(
                forward_file, reverse_file, str(sample_dir)
            )

            filtered_forward = read_fastq(filtered_forward_path)
            filtered_reverse = read_fastq(filtered_reverse_path)

            # Align lengths in case downstream tools trimmed unevenly
            pairable_count = min(len(filtered_forward), len(filtered_reverse))
            if len(filtered_forward) != len(filtered_reverse):
                logger.warning(
                    "Mismatch in filtered paired reads: %d forward vs %d reverse; using first %d pairs",
                    len(filtered_forward), len(filtered_reverse), pairable_count
                )
                filtered_forward = filtered_forward[:pairable_count]
                filtered_reverse = filtered_reverse[:pairable_count]

            qc_stats = {
                "step": "quality_control",
                "forward_input_sequences": len(forward_raw),
                "reverse_input_sequences": len(reverse_raw),
                "forward_output_sequences": len(filtered_forward),
                "reverse_output_sequences": len(filtered_reverse),
                "filtered_forward_file": filtered_forward_path,
                "filtered_reverse_file": filtered_reverse_path
            }
            results["processing_steps"].append(qc_stats)

            logger.info("Step 2: Merging paired reads")
            merged_sequences, merge_stats = self._merge_pair_sequences(
                forward_fastq=Path(filtered_forward_path),
                reverse_fastq=Path(filtered_reverse_path),
                sample_id=sample_id,
                output_dir=sample_dir,
                temp_dir=temp_merge_dir,
            )
            cleanup_temp_dir = True

            merged_file = sample_dir / "merged_reads.fasta"
            write_fasta(merged_sequences, merged_file)

            merge_stats.update({
                "step": "pair_merging",
                "output_file": str(merged_file),
            })
            results["processing_steps"].append(merge_stats)
            results["merged_sequences"] = merged_sequences

            if not merged_sequences:
                raise RuntimeError("No merged sequences available after pairing step")

            logger.info("Step 3: Denoising and ASV generation")
            asvs, abundance_table = self.denoiser.denoise(merged_sequences)

            asv_file = sample_dir / "asvs.fasta"
            write_fasta(asvs, asv_file)

            denoise_stats = {
                "step": "denoising",
                "method": type(self.denoiser).__name__,
                "input_sequences": len(merged_sequences),
                "output_asvs": len(asvs),
                "output_file": str(asv_file),
                "abundance_table": abundance_table
            }
            results["processing_steps"].append(denoise_stats)

            if self.remove_chimeras:
                logger.info("Step 4: Chimera detection and removal")
                clean_asvs, chimeric_ids = self.chimera_remover.remove_chimeras(
                    asvs, abundance_table
                )

                clean_asv_file = sample_dir / "asvs_no_chimeras.fasta"
                write_fasta(clean_asvs, clean_asv_file)

                clean_abundance_table = {
                    asv_id: count for asv_id, count in abundance_table.items()
                    if asv_id not in chimeric_ids
                }

                chimera_stats = {
                    "step": "chimera_removal",
                    "input_asvs": len(asvs),
                    "output_asvs": len(clean_asvs),
                    "chimeric_asvs": len(chimeric_ids),
                    "output_file": str(clean_asv_file),
                    "abundance_table": clean_abundance_table
                }
                results["processing_steps"].append(chimera_stats)

                final_asvs = clean_asvs
                final_abundance_table = clean_abundance_table
                final_asv_file = clean_asv_file
            else:
                final_asvs = asvs
                final_abundance_table = abundance_table
                final_asv_file = asv_file

            results.update({
                "final_asvs": len(final_asvs),
                "final_asv_file": str(final_asv_file),
                "abundance_table": final_abundance_table,
                "success": True
            })

            abundance_file = sample_dir / "abundance_table.txt"
            self._save_abundance_table(final_abundance_table, abundance_file)
            results["abundance_file"] = str(abundance_file)

            summary_stats = self._generate_summary_stats(results)
            results["summary_stats"] = summary_stats

            log_file = sample_dir / "preprocessing_log.txt"
            self._save_processing_log(results, log_file)
            results["log_file"] = str(log_file)

            if cleanup_temp_dir:
                shutil.rmtree(temp_merge_dir)

            logger.info(f"Paired-end preprocessing completed successfully for {sample_id}")
            logger.info(f"Final output: {len(final_asvs)} ASVs")

        except Exception as exc:
            logger.error(f"Paired-end preprocessing failed for {sample_id}: {exc}")
            results["success"] = False
            results["error"] = str(exc)
            raise

        return results

    def _build_vsearch_merge_cmd(
        self,
        forward_reads: Path,
        reverse_reads: Path,
        merged_output: Path,
        unmerged_fwd_output: Path,
        unmerged_rev_output: Path,
        logfile_path: Path,
    ) -> List[str]:
        """Build the VSEARCH merge command with config-driven defaults."""
        cfg = self.preprocessing_config
        cpu_count = int(cfg.get("merge_threads", cfg.get("threads", os.cpu_count() or 1)))
        min_overlap = int(cfg.get("merge_min_overlap", cfg.get("paired_min_overlap", 10)))
        max_diffs = int(cfg.get("merge_max_diffs", cfg.get("paired_max_mismatches", 5)))

        return [
            "vsearch",
            "--fastq_mergepairs", str(forward_reads),
            "--reverse", str(reverse_reads),
            "--fastqout", str(merged_output),
            "--fastqout_notmerged_fwd", str(unmerged_fwd_output),
            "--fastqout_notmerged_rev", str(unmerged_rev_output),
            "--fastq_minovlen", str(min_overlap),
            "--fastq_maxdiffs", str(max_diffs),
            "--threads", str(cpu_count),
            "--log", str(logfile_path),
        ]
    
    def _save_abundance_table(self, abundance_table: Dict[str, int], output_file: str):
        """Save abundance table to file."""
        with open(output_file, 'w') as f:
            f.write("ASV_ID\tAbundance\n")
            for asv_id, abundance in sorted(abundance_table.items()):
                f.write(f"{asv_id}\t{abundance}\n")
    
    def _generate_summary_stats(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics from processing results."""
        stats = {
            "sample_id": results["sample_id"],
            "total_processing_steps": len(results["processing_steps"]),
            "final_asvs": results.get("final_asvs", 0)
        }
        
        # Extract statistics from each processing step
        for step in results["processing_steps"]:
            step_name = step["step"]
            if "input_sequences" in step:
                stats[f"{step_name}_input"] = step["input_sequences"]
            if "output_sequences" in step:
                stats[f"{step_name}_output"] = step["output_sequences"]
            if "output_asvs" in step:
                stats[f"{step_name}_output"] = step["output_asvs"]
        
        return stats
    
    def _save_processing_log(self, results: Dict[str, Any], log_file: str):
        """Save processing log to file."""
        with open(log_file, 'w') as f:
            f.write(f"Preprocessing Log for Sample: {results['sample_id']}\n")
            f.write("=" * 50 + "\n\n")

            input_info = results.get("input_file") or results.get("input_files")
            if isinstance(input_info, dict):
                f.write("Input files:\n")
                for role, path in input_info.items():
                    f.write(f"  {role}: {path}\n")
            else:
                f.write(f"Input file: {input_info}\n")

            f.write(f"Output directory: {results['output_dir']}\n")
            f.write(f"Success: {results.get('success', False)}\n\n")
            
            f.write("Processing Steps:\n")
            f.write("-" * 20 + "\n")
            
            for i, step in enumerate(results["processing_steps"], 1):
                f.write(f"{i}. {step['step'].title()}\n")
                for key, value in step.items():
                    if key != "step":
                        f.write(f"   {key}: {value}\n")
                f.write("\n")
            
            if "summary_stats" in results:
                f.write("Summary Statistics:\n")
                f.write("-" * 20 + "\n")
                for key, value in results["summary_stats"].items():
                    f.write(f"{key}: {value}\n")

    def _merge_pair_sequences(
        self,
        forward_fastq: Path,
        reverse_fastq: Path,
        sample_id: str,
        output_dir: Path,
        temp_dir: Path,
    ) -> Tuple[List[SeqRecord], Dict[str, Any]]:
        """Merge paired-end FASTQ files via VSEARCH, falling back to PEAR."""
        merged_fastq = temp_dir / f"{sample_id}.merged.fastq"
        vsearch_log = temp_dir / f"{sample_id}.vsearch.log"
        unmerged_fwd = temp_dir / f"{sample_id}.unmerged_fwd.fastq"
        unmerged_rev = temp_dir / f"{sample_id}.unmerged_rev.fastq"
        unmerged_combined = output_dir / f"{sample_id}.unmerged.fastq"

        cfg = self.preprocessing_config
        cpu_count = int(cfg.get("merge_threads", cfg.get("threads", os.cpu_count() or 1)))

        total_pairs = 0
        merged_count = 0

        vsearch_exe = shutil.which("vsearch")
        pear_exe = shutil.which("pear")

        if vsearch_exe:
            cmd = self._build_vsearch_merge_cmd(
                forward_reads=forward_fastq,
                reverse_reads=reverse_fastq,
                merged_output=merged_fastq,
                unmerged_fwd_output=unmerged_fwd,
                unmerged_rev_output=unmerged_rev,
                logfile_path=vsearch_log,
            )

            # Use resolved executable path while keeping helper output deterministic for tests.
            cmd[0] = vsearch_exe
            try:
                subprocess.run(cmd, capture_output=True, check=True, text=True)
            except subprocess.CalledProcessError as err:
                raise RuntimeError(
                    f"VSEARCH merge failed for sample {sample_id}: {err.stderr or err.stdout}"
                ) from err

            if vsearch_log.exists():
                log_text = vsearch_log.read_text(encoding="utf-8", errors="ignore")
                total_pairs_match = re.search(r"Pairs\s*:\s*(\d+)", log_text, re.IGNORECASE)
                merged_match = re.search(r"Merged\s*:\s*(\d+)", log_text, re.IGNORECASE)
                if total_pairs_match:
                    total_pairs = int(total_pairs_match.group(1))
                if merged_match:
                    merged_count = int(merged_match.group(1))
        elif pear_exe:
            pear_prefix = temp_dir / f"{sample_id}.pear"
            pear_cmd = [
                pear_exe,
                "-f", str(forward_fastq),
                "-r", str(reverse_fastq),
                "-o", str(pear_prefix),
                "-j", str(cpu_count),
                "-v", str(int(cfg.get("merge_min_overlap", cfg.get("paired_min_overlap", 10)))),
                "-n", str(int(cfg.get("pear_min_assembled_length", 50))),
            ]
            try:
                pear_result = subprocess.run(pear_cmd, capture_output=True, check=True, text=True)
            except subprocess.CalledProcessError as err:
                raise RuntimeError(
                    f"PEAR merge failed for sample {sample_id}: {err.stderr or err.stdout}"
                ) from err

            merged_fastq = pear_prefix.with_name(f"{pear_prefix.name}.assembled.fastq")
            unmerged_fwd = pear_prefix.with_name(f"{pear_prefix.name}.unassembled.forward.fastq")
            unmerged_rev = pear_prefix.with_name(f"{pear_prefix.name}.unassembled.reverse.fastq")

            stdout_text = pear_result.stdout or ""
            total_match = re.search(r"Assembled\s+reads\s*:\s*\d+\s*/\s*(\d+)", stdout_text, re.IGNORECASE)
            assembled_match = re.search(r"Assembled\s+reads\s*:\s*(\d+)", stdout_text, re.IGNORECASE)
            if total_match:
                total_pairs = int(total_match.group(1))
            if assembled_match:
                merged_count = int(assembled_match.group(1))
        else:
            raise RuntimeError(
                "No paired-read merge tool found. Install VSEARCH (preferred) or PEAR and ensure the "
                "binary is available in PATH. Example: 'sudo apt install vsearch' or install PEAR."
            )

        merged_records = read_fastq(merged_fastq) if merged_fastq.exists() else []
        unmerged_records: List[SeqRecord] = []
        if unmerged_fwd.exists():
            unmerged_records.extend(read_fastq(unmerged_fwd))
        if unmerged_rev.exists():
            unmerged_records.extend(read_fastq(unmerged_rev))

        write_fastq(unmerged_records, unmerged_combined)

        # Fallback statistics if log parsing did not match the current tool output format.
        if merged_count == 0:
            merged_count = len(merged_records)
        if total_pairs == 0:
            total_pairs = merged_count + max(len(unmerged_records) // 2, 0)

        unmerged_pairs = max(total_pairs - merged_count, 0)
        merge_rate = (merged_count / total_pairs * 100.0) if total_pairs > 0 else 0.0

        logger.info(
            "Merged %d/%d read pairs (%.2f%%) for sample %s",
            merged_count,
            total_pairs,
            merge_rate,
            sample_id,
        )
        if merge_rate < 70.0:
            logger.warning("Low merge rate for %s: %.2f%%", sample_id, merge_rate)
        if unmerged_pairs > 0:
            logger.warning("%d reads could not be merged and were discarded", unmerged_pairs)

        self.stats["merged_reads"] = merged_count
        self.stats["merge_rate"] = merge_rate

        return merged_records, {
            "merged_reads": merged_count,
            "total_pairs": total_pairs,
            "merge_rate": merge_rate,
            "unmerged_reads": unmerged_pairs,
            "unmerged_file": str(unmerged_combined),
        }