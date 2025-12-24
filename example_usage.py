#!/usr/bin/env python3
"""
Example Usage for eDNA Analysis Pipeline

This script demonstrates how to use the eDNA analysis pipeline
with reference databases for taxonomic classification.
"""

import os
import sys
import logging
import tempfile
from pathlib import Path
import argparse
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
import numpy as np
import random

# Add the pipeline directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "edna_pipeline"))

from database_manager import DatabaseManager
from taxonomic_assignment import TaxonomicAssigner

# Basic logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_sample_data(output_dir: str, num_sequences: int = 10, seed: int = 42):
    """Create sample FASTA data for testing."""
    random.seed(seed)
    np.random.seed(seed)
    
    output_path = Path(output_dir) / "sample_data.fasta"
    
    # Define some common marine organisms for more realistic data
    marine_organisms = [
        ("Prochlorococcus marinus", "Bacteria"),  # Marine cyanobacterium
        ("Pelagibacter ubique", "Bacteria"),  # Most abundant marine bacterium
        ("Thalassiosira pseudonana", "Eukaryota"),  # Marine diatom
        ("Phaeodactylum tricornutum", "Eukaryota"),  # Marine diatom
        ("Emiliania huxleyi", "Eukaryota"),  # Coccolithophore
        ("Methanococcoides burtonii", "Archaea"),  # Marine archaea
        ("Pyrococcus furiosus", "Archaea"),  # Marine archaea
        ("Vibrio fischeri", "Bacteria"),  # Bioluminescent marine bacterium
        ("Marinobacter hydrocarbonoclasticus", "Bacteria"),  # Oil-degrading bacterium
        ("Nitrosopumilus maritimus", "Archaea")  # Ammonia-oxidizing archaea
    ]
    
    # Generate sample sequences
    sequences = []
    for i in range(num_sequences):
        # Select a random organism or generate random sequence
        if random.random() < 0.7:  # 70% chance of using a known organism
            organism, domain = random.choice(marine_organisms)
            id_name = f"{organism.replace(' ', '_')}_{i+1}"
            description = f"{domain}; {organism}"
        else:
            id_name = f"Unknown_sequence_{i+1}"
            description = "Unknown marine organism"
            
        # Generate random sequence (simulating 16S rRNA, ~1500bp)
        seq_length = random.randint(1000, 2000)
        bases = ['A', 'T', 'G', 'C']
        seq = ''.join(random.choices(bases, k=seq_length))
        
        # Create SeqRecord
        record = SeqRecord(
            Seq(seq),
            id=id_name,
            name=id_name,
            description=description
        )
        sequences.append(record)
        
    # Write to file
    SeqIO.write(sequences, output_path, "fasta")
    logger.info(f"Created sample data with {num_sequences} sequences at {output_path}")
    
    return output_path

def check_database_availability(db_manager: DatabaseManager):
    """Check if required databases are available and print status."""
    info = db_manager.get_database_info()
    
    # Critical databases for basic operation
    critical_dbs = ["taxdb", "16S_ribosomal_RNA"]
    recommended_dbs = ["18S_fungal_sequences", "28S_fungal_sequences", "ITS_eukaryote_sequences"]
    
    missing_critical = []
    missing_recommended = []
    available_dbs = []
    
    for db in critical_dbs:
        status = info[db].get("status", "not_downloaded")
        if status != "complete":
            missing_critical.append(db)
        else:
            available_dbs.append(db)
            
    for db in recommended_dbs:
        status = info[db].get("status", "not_downloaded")
        if status != "complete":
            missing_recommended.append(db)
        else:
            available_dbs.append(db)
    
    print("\nDATABASE STATUS")
    print("=" * 30)
    
    if missing_critical:
        print(f"\n❌ Missing critical databases: {', '.join(missing_critical)}")
        print("   These are required for basic operation!")
        print("   To download them: python setup_databases.py --databases " + " ".join(missing_critical))
    else:
        print("✅ All critical databases are available")
        
    if missing_recommended:
        print(f"\n⚠️ Missing recommended databases: {', '.join(missing_recommended)}")
        print("   These provide better classification results")
        print("   To download them: python setup_databases.py --databases " + " ".join(missing_recommended))
    else:
        print("✅ All recommended databases are available")
    
    print(f"\nAvailable databases: {', '.join(available_dbs)}")
    
    return len(missing_critical) == 0, available_dbs

def run_taxonomic_assignment(db_manager: DatabaseManager, input_fasta: str, output_dir: str):
    """Run taxonomic assignment on input sequences."""
    assigner = TaxonomicAssigner(db_manager)
    
    # Load sequences
    sequences = list(SeqIO.parse(input_fasta, "fasta"))
    logger.info(f"Loaded {len(sequences)} sequences from {input_fasta}")
    
    # Run taxonomic assignment
    logger.info("Running taxonomic assignment...")
    results = assigner.assign_taxonomy(sequences, methods=['blast', 'kmer'])
    
    # Save results
    output_path = Path(output_dir) / "taxonomic_assignments.csv"
    assigner.save_results(results, str(output_path))
    
    # Generate summary report
    summary = assigner.generate_summary_report(results)
    
    print("\nTAXONOMIC ASSIGNMENT SUMMARY")
    print("=" * 30)
    print(f"Total sequences processed: {summary['total_sequences']}")
    print(f"Mean confidence score: {summary['mean_confidence']:.2f}%")
    
    # Print classification success rates
    print("\nClassification success rates:")
    for level, rate in summary['classification_success_rates'].items():
        print(f"  {level.capitalize():10}: {rate:.1f}%")
    
    # Print top taxa at kingdom level
    print("\nTop kingdoms detected:")
    if 'kingdom' in summary['taxonomic_diversity']:
        kingdom_counts = summary['taxonomic_diversity']['kingdom']
        sorted_kingdoms = sorted(kingdom_counts.items(), key=lambda x: x[1], reverse=True)
        for kingdom, count in sorted_kingdoms[:5]:  # Show top 5
            percent = (count / summary['total_sequences']) * 100
            print(f"  {kingdom:15}: {count} sequences ({percent:.1f}%)")
    
    return output_path, summary

def main():
    parser = argparse.ArgumentParser(description="Example usage of eDNA analysis pipeline")
    
    parser.add_argument(
        '--input', '-i',
        help='Input FASTA file with sequences to analyze'
    )
    
    parser.add_argument(
        '--output-dir', '-o',
        default='results',
        help='Directory for output files (default: results)'
    )
    
    parser.add_argument(
        '--db-dir',
        default='databases',
        help='Directory containing reference databases (default: databases)'
    )
    
    parser.add_argument(
        '--create-sample',
        type=int,
        default=0,
        help='Create sample data with specified number of sequences (default: 0, disabled)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Initialize database manager
    db_manager = DatabaseManager(args.db_dir)
    
    # Check database availability
    databases_ok, available_dbs = check_database_availability(db_manager)
    
    if not databases_ok:
        logger.warning("Some critical databases are missing. Run setup_databases.py to download them.")
        response = input("Continue anyway? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            logger.info("Exiting. Please download required databases and try again.")
            return 1
    
    # Create or use sample data
    if args.create_sample > 0:
        logger.info(f"Creating sample data with {args.create_sample} sequences")
        input_fasta = create_sample_data(args.output_dir, args.create_sample)
    elif args.input:
        input_fasta = args.input
    else:
        # No input file and no sample requested
        logger.error("No input file specified. Use --input or --create-sample.")
        return 1
    
    # Run taxonomic assignment
    results_file, summary = run_taxonomic_assignment(db_manager, input_fasta, args.output_dir)
    
    print(f"\nResults saved to {results_file}")
    print(f"Results directory: {output_dir}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())