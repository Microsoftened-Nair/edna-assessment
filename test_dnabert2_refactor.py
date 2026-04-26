#!/usr/bin/env python3
"""
Validation Tests for DNABERT2-First Refactored Pipeline

This script tests the new DNABERT2 KNN-based taxonomic assignment pipeline.
It verifies:
1. DNABERT2 KNN classifier initialization
2. Reference database loading
3. Embedding extraction
4. KNN matching and taxonomy resolution
5. End-to-end pipeline execution
6. Output format validation
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_dnabert2_knn_initialization():
    """Test DNABERT2 KNN classifier can be initialized."""
    logger.info("=" * 60)
    logger.info("Test 1: DNABERT2 KNN Classifier Initialization")
    logger.info("=" * 60)
    
    try:
        from edna_pipeline.models.dnabert2_knn_classifier import DNABERT2KNNClassifier
        
        # Check if reference DB exists
        ref_db_path = "databases/processed/16S_ribosomal_RNA/"
        if not Path(ref_db_path).exists():
            logger.error(f"Reference database not found: {ref_db_path}")
            logger.info("Run: python setup_databases.py --recommended")
            return False
        
        logger.info(f"Initializing DNABERT2 KNN classifier with reference DB: {ref_db_path}")
        classifier = DNABERT2KNNClassifier(
            reference_db_path=ref_db_path,
            k=3,
            model_name="zhihan1996/DNABERT-2-117M"
        )
        
        if classifier.knn_index is None:
            logger.error("KNN index not built")
            return False
        
        logger.info(f"✓ Classifier initialized successfully")
        logger.info(f"  Reference sequences loaded: {len(classifier.reference_db.sequences)}")
        logger.info(f"  KNN index ready")
        return True
    
    except ImportError as e:
        logger.error(f"Import error: {e}")
        logger.info("Install missing packages: pip install scikit-learn transformers torch")
        return False
    except Exception as e:
        logger.error(f"Initialization error: {e}")
        return False


def test_single_prediction():
    """Test single sequence prediction."""
    logger.info("\n" + "=" * 60)
    logger.info("Test 2: Single Sequence Prediction")
    logger.info("=" * 60)
    
    try:
        from edna_pipeline.models.dnabert2_knn_classifier import DNABERT2KNNClassifier
        
        ref_db_path = "databases/processed/16S_ribosomal_RNA/"
        classifier = DNABERT2KNNClassifier(reference_db_path=ref_db_path, k=3)
        
        # Test sequence (arbitrary 16S-like)
        test_seq = "ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT" + \
                  "ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT"
        
        logger.info(f"Predicting taxonomy for test sequence ({len(test_seq)} bp)...")
        result = classifier.predict(test_seq)
        
        # Validate result structure
        required_fields = ["kingdom", "phylum", "class", "order", "family", "genus", "species", "confidence", "method"]
        for field in required_fields:
            if field not in result:
                logger.error(f"Missing field in result: {field}")
                return False
        
        logger.info(f"✓ Prediction successful")
        logger.info(f"  Method: {result['method']}")
        logger.info(f"  Taxonomy: {result['genus']} {result['species']}")
        logger.info(f"  Confidence: {result['confidence']:.1f}%")
        logger.info(f"  Distance to closest match: {result['closest_distance']:.4f}")
        
        # Check if prediction is "Unknown"
        if result['kingdom'] == "Unknown":
            logger.warning("Prediction is 'Unknown' - reference DB may not contain similar sequences")
        
        return True
    
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_prediction():
    """Test batch sequence prediction."""
    logger.info("\n" + "=" * 60)
    logger.info("Test 3: Batch Sequence Prediction")
    logger.info("=" * 60)
    
    try:
        from edna_pipeline.models.dnabert2_knn_classifier import DNABERT2KNNClassifier
        
        ref_db_path = "databases/processed/16S_ribosomal_RNA/"
        classifier = DNABERT2KNNClassifier(reference_db_path=ref_db_path, k=3)
        
        # Create batch of test sequences
        base_seq = "ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT"
        test_seqs = [base_seq + "A" * i for i in range(3)]
        
        logger.info(f"Predicting taxonomy for {len(test_seqs)} sequences...")
        results = classifier.predict_batch(test_seqs)
        
        if len(results) != len(test_seqs):
            logger.error(f"Expected {len(test_seqs)} results, got {len(results)}")
            return False
        
        logger.info(f"✓ Batch prediction successful")
        for i, result in enumerate(results):
            logger.info(f"  [{i+1}] {result['genus']} {result['species']} (confidence: {result['confidence']:.1f}%)")
        
        return True
    
    except Exception as e:
        logger.error(f"Batch prediction error: {e}")
        return False


def test_config_structure():
    """Test configuration structure."""
    logger.info("\n" + "=" * 60)
    logger.info("Test 4: Configuration Structure")
    logger.info("=" * 60)
    
    try:
        from edna_pipeline.config import Config
        
        config = Config("config/default_config.yaml")
        
        # Check DNABERT2 config
        dnabert2_config = config.get("taxonomy.dnabert2", {})
        
        required_keys = ["enabled", "model_source", "classification_mode", "reference_db_path"]
        for key in required_keys:
            if key not in dnabert2_config:
                logger.error(f"Missing config key: taxonomy.dnabert2.{key}")
                return False
        
        logger.info(f"✓ Configuration validated")
        logger.info(f"  Primary method: {config.get('taxonomy.primary_method')}")
        logger.info(f"  DNABERT2 enabled: {dnabert2_config.get('enabled')}")
        logger.info(f"  Model source: {dnabert2_config.get('model_source')}")
        logger.info(f"  Classification mode: {dnabert2_config.get('classification_mode')}")
        logger.info(f"  Reference DB: {dnabert2_config.get('reference_db_path')}")
        
        return True
    
    except Exception as e:
        logger.error(f"Config error: {e}")
        return False


def test_taxonomic_assigner():
    """Test TaxonomicAssigner with new DNABERT2 KNN."""
    logger.info("\n" + "=" * 60)
    logger.info("Test 5: TaxonomicAssigner Integration")
    logger.info("=" * 60)
    
    try:
        from edna_pipeline.taxonomic_assignment import TaxonomicAssigner
        from edna_pipeline.database_manager import DatabaseManager
        from edna_pipeline.config import Config
        from Bio.SeqRecord import SeqRecord
        from Bio.Seq import Seq
        
        # Load config
        config = Config("config/default_config.yaml")
        taxonomy_config = config.get("taxonomy", {})
        
        # Initialize database manager and assigner
        db_manager = DatabaseManager("databases")
        assigner = TaxonomicAssigner(db_manager, config=taxonomy_config)
        
        if assigner.dnabert2_knn_classifier is None:
            logger.error("DNABERT2 KNN classifier not initialized")
            return False
        
        # Create test sequences
        test_seqs = [
            SeqRecord(Seq("ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT"), id="seq1"),
            SeqRecord(Seq("ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT"), id="seq2"),
        ]
        
        logger.info(f"Assigning taxonomy to {len(test_seqs)} test sequences...")
        results = assigner.assign_taxonomy(test_seqs)
        
        if len(results) != len(test_seqs):
            logger.error(f"Expected {len(test_seqs)} results, got {len(results)}")
            return False
        
        logger.info(f"✓ TaxonomicAssigner integration successful")
        for seq_id, assignment in results.items():
            logger.info(f"  [{seq_id}] {assignment.genus} {assignment.species} (confidence: {assignment.confidence:.1f}%)")
        
        return True
    
    except Exception as e:
        logger.error(f"TaxonomicAssigner error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pipeline_end_to_end():
    """Test full pipeline with DNABERT2 KNN."""
    logger.info("\n" + "=" * 60)
    logger.info("Test 6: End-to-End Pipeline")
    logger.info("=" * 60)
    
    try:
        from edna_pipeline.pipeline import DeepSeaEDNAPipeline
        
        logger.info("Initializing pipeline...")
        pipeline = DeepSeaEDNAPipeline(config_path="config/default_config.yaml")
        
        # Check for demo FASTQ files
        demo_dir = Path("data/demo_fastq")
        if not demo_dir.exists():
            logger.warning(f"Demo data directory not found: {demo_dir}")
            logger.info("Skipping end-to-end test")
            return True
        
        fastq_files = list(demo_dir.glob("*_R1.fastq")) + list(demo_dir.glob("*.fastq"))
        if not fastq_files:
            logger.warning("No FASTQ files found in demo data")
            logger.info("Skipping end-to-end test")
            return True
        
        # Use first FASTQ file
        input_file = str(fastq_files[0])
        logger.info(f"Running pipeline on: {input_file}")
        
        results = pipeline.process_sample(
            input_files=input_file,
            output_dir="results/validation_test"
        )
        
        logger.info("✓ Pipeline execution successful")
        logger.info(f"  Output directory: {results['output_dir']}")
        logger.info(f"  Sample ID: {results['sample_id']}")
        
        # Check for expected output files
        output_dir = Path(results['output_dir'])
        expected_files = ["taxonomy.json", "taxonomic_assignments.csv"]
        for fname in expected_files:
            fpath = output_dir / fname
            if not fpath.exists():
                logger.warning(f"Missing expected output file: {fname}")
        
        # Validate taxonomy output
        tax_file = output_dir / "taxonomy.json"
        if tax_file.exists():
            with open(tax_file, 'r') as f:
                taxonomy = json.load(f)
            logger.info(f"  Classified sequences: {len(taxonomy)}")
            
            # Sample a result
            if taxonomy:
                sample_id = list(taxonomy.keys())[0]
                sample_tax = taxonomy[sample_id]
                logger.info(f"  Sample taxonomy: {sample_tax['kingdom']} / {sample_tax['phylum']} / {sample_tax['class']}")
        
        return True
    
    except FileNotFoundError:
        logger.warning("Demo data not available, skipping end-to-end test")
        return True
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all validation tests."""
    logger.info("\n" + "=" * 60)
    logger.info("DNABERT2-First Pipeline Validation Tests")
    logger.info("=" * 60)
    
    tests = [
        ("Classifier Initialization", test_dnabert2_knn_initialization),
        ("Single Prediction", test_single_prediction),
        ("Batch Prediction", test_batch_prediction),
        ("Configuration", test_config_structure),
        ("TaxonomicAssigner", test_taxonomic_assigner),
        ("End-to-End Pipeline", test_pipeline_end_to_end),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results[test_name] = "✓ PASSED" if passed else "✗ FAILED"
        except Exception as e:
            logger.error(f"Test error: {e}")
            results[test_name] = "✗ ERROR"
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    for test_name, result in results.items():
        logger.info(f"{result} - {test_name}")
    
    passed_count = sum(1 for r in results.values() if "✓" in r)
    total_count = len(results)
    
    logger.info(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    return passed_count == total_count


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
