import re

with open("edna_pipeline/pipeline.py", "r") as f:
    pipeline_code = f.read()

patch = """
            # Step 1: Preprocessing
            logger.info("Step 1: Sequence preprocessing")
            
            is_fasta_input = False
            if input_type == "single" and str(input_file).lower().endswith((".fasta", ".fa")):
                is_fasta_input = True
                
            if is_fasta_input:
                logger.info("Direct FASTA input detected, skipping FASTQ preprocessing.")
                # We mock the preprocessing results to pass the FASTA directly as the ASV file
                asv_file = os.path.join(sample_output_dir, f"{sample_id}_input.fasta")
                import shutil
                shutil.copy(input_file, asv_file)
                
                # Mock abundance table (each seq count = 1)
                from Bio import SeqIO
                abundance_table = {rec.id: 1 for record in SeqIO.parse(asv_file, "fasta") for rec in [record]}
                
                preprocessing_results = {
                    "success": True,
                    "final_asv_file": asv_file,
                    "abundance_table": abundance_table,
                    "summary_stats": {
                        "input_reads": len(abundance_table),
                        "retained_reads": len(abundance_table),
                        "retention_rate": 100.0,
                        "unique_asvs": len(abundance_table)
                    }
                }
            else:
                if input_type == "paired":
                    preprocessing_results = self.preprocessor.process_paired_end_reads(
                        forward_file, reverse_file, sample_output_dir, sample_id
                    )
                else:
                    preprocessing_results = self.preprocessor.process_single_end_reads(
                        input_file, sample_output_dir, sample_id
                    )
"""

# Find where to inject
old_code = """
            # Step 1: Preprocessing
            logger.info("Step 1: Sequence preprocessing")
            if input_type == "paired":
                preprocessing_results = self.preprocessor.process_paired_end_reads(
                    forward_file, reverse_file, sample_output_dir, sample_id
                )
            else:
                preprocessing_results = self.preprocessor.process_single_end_reads(
                    input_file, sample_output_dir, sample_id
                )
"""

pipeline_code = pipeline_code.replace(old_code.strip(), patch.strip())

with open("edna_pipeline/pipeline.py", "w") as f:
    f.write(pipeline_code)

