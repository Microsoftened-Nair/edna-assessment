import sys
import os
import tempfile
import logging
from pathlib import Path
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio import SeqIO

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.WARNING)

dummy_fastq = """@SEQ_ID
GATTTGGGGTTCAAAGCAGTATCGATCAAATAGTAAATCCATTTGTTCAACTCACAGTTT
+
!''*((((***+))%%%++)(%%%%).1***-+*''))**55CCF>>>>>>CCCCCCC65
"""

dummy_fasta = """>SEQ_ID
GATTTGGGGTTCAAAGCAGTATCGATCAAATAGTAAATCCATTTGTTCAACTCACAGTTT
"""

def test_imports():
    print("\n--- Testing Imports ---")
    imports = ["numpy", "pandas", "scipy", "Bio", "sklearn", "umap", "torch", "transformers", "rpy2", "joblib"]
    success = True
    for imp in imports:
        try:
            __import__(imp)
            print(f"✓ {imp} imported successfully.")
        except ImportError as e:
            print(f"✗ Failed to import {imp}: {e}")
            success = False
    return success

def test_kmer():
    print("\n--- Testing K-mer ML Classifier ---")
    from edna_pipeline.models.classifier import RandomForestKmerClassifier
    try:
        classifier = RandomForestKmerClassifier(k=4)
        print("✓ Classifier initialized")
        # Train on mock data
        import random
        classifier.train(
            sequences=["ACGTACGTACGT", "TGCATGCATGCA", "GATCGATC", "AATTAATT"],
            labels=["A;B;C", "X;Y;Z", "A;B;C", "X;Y;Z"],
            model_path=Path("/tmp/mock_model.joblib"),
            n_estimators=5
        )
        print("✓ Classifier trained mock model")
        res = classifier.predict("ACGTACGTACGT")
        if "confidence_score" in res:
            print("✓ Classifier predict output format correct.")
        else:
            print("✗ Classifier predict output unexpected:", res)
    except Exception as e:
        print(f"✗ K-mer ML failed: {e}")

def test_taxonomy():
    print("\n--- Testing Taxonomy Resolution ---")
    from edna_pipeline.taxonomic_assignment import TaxonomicAssigner
    try:
        assigner = TaxonomicAssigner()
        # Mock hit
        hit = {"staxids": "2", "pident": "99.0", "evalue": "0.0"}
        tax = assigner._get_taxonomy_from_hit(hit)
        if "kingdom" in tax:
            print("✓ Taxonomy format correct:", tax)
        else:
            print("✗ Taxonomy format incorrect:", tax)
    except Exception as e:
        print("✗ Taxonomy test failed:", e)

def test_chimera():
    print("\n--- Testing Chimera Removal ---")
    try:
        from edna_pipeline.preprocessing.chimera_removal import ChimeraRemover
        remover = ChimeraRemover({"min_abundance_ratio": 2.0})
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, "input.fasta")
            output_file = os.path.join(tmpdir, "output.fasta")
            with open(input_file, "w") as f:
                f.write(">seq1\nACGTACGTACGT\n")
            res = remover.remove_chimeras_vsearch(input_file, output_file)
            print(f"✓ Chimera vsearch test ran (vsearch return status): {res}")
    except Exception as e:
        print(f"✗ Chimera test failed: {e}")

def test_denoising():
    print("\n--- Testing Denoising ---")
    from edna_pipeline.preprocessing.denoising import DenoiseDADA2
    config = {"threads": 1, "unoise_alpha": 2.0, "min_size": 1, "min_unique_size": 1}
    denoiser = DenoiseDADA2(config)
    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = os.path.join(tmpdir, "input.fasta")
        with open(input_file, "w") as f:
            f.write(dummy_fasta)
        try:
            res = denoiser.denoise(input_file)
            print("✓ Denoising executed, stats:", res.get("stats"))
        except Exception as e:
            print(f"✗ Denoising test failed: {e}")

def test_paired_merging():
    print("\n--- Testing Paired Merging ---")
    from edna_pipeline.preprocessing.preprocessor import SequencePreprocessor
    cfg = {"preprocessing": {"threads": 1, "merge_min_overlap": 5}}
    sp = SequencePreprocessor(cfg)
    with tempfile.TemporaryDirectory() as tmpdir:
        fwd = os.path.join(tmpdir, "fwd.fastq")
        rev = os.path.join(tmpdir, "rev.fastq")
        with open(fwd, "w") as f: f.write(dummy_fastq)
        with open(rev, "w") as f: f.write(dummy_fastq)
        try:
            records, stats = sp._merge_pair_sequences(Path(fwd), Path(rev), "sample1", Path(tmpdir), Path(tmpdir))
            print("✓ Paired merging ran, stats:", stats)
        except Exception as e:
            print(f"✗ Paired merging failed: {e}")

if __name__ == "__main__":
    test_imports()
    test_kmer()
    test_taxonomy()
    test_chimera()
    test_denoising()
    test_paired_merging()
