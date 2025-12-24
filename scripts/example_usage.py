#!/usr/bin/env python3
"""
Example script demonstrating usage of the AI-driven deep-sea eDNA analysis pipeline.

This script shows how to:
1. Initialize the pipeline with configuration
2. Process single samples  
3. Process batches of samples
4. Analyze results
"""

import os
import sys
from pathlib import Path

# Add the pipeline to Python path
sys.path.append(str(Path(__file__).parent.parent))

from edna_pipeline import DeepSeaEDNAPipeline


def example_single_sample():
    """Example: Process a single sample."""
    print("=== Single Sample Processing Example ===")
    
    # Initialize pipeline with default configuration
    pipeline = DeepSeaEDNAPipeline()
    
    # Example with single-end reads
    # Replace with actual path to your FASTQ file
    sample_file = "data/sample_R1.fastq"  # This would be your actual file
    
    if os.path.exists(sample_file):
        try:
            # Process the sample
            results = pipeline.process_sample(
                input_files=sample_file,
                sample_id="deep_sea_sample_001",
                output_dir="results/single_sample"
            )
            
            # Print summary
            print(f"Processing successful: {results['success']}")
            print(f"Sample ID: {results['sample_id']}")
            print(f"Processing time: {results.get('processing_time', 'N/A'):.2f} seconds")
            
            # Show pipeline steps
            print("\nPipeline steps completed:")
            for step in results['pipeline_steps']:
                print(f"  - {step['step']}: {step['status']}")
            
            print(f"\nResults saved to: {results['output_dir']}")
            
        except Exception as e:
            print(f"Processing failed: {e}")
    else:
        print(f"Sample file not found: {sample_file}")
        print("Please provide a valid FASTQ file path")


def example_paired_end():
    """Example: Process paired-end reads."""
    print("\n=== Paired-End Sample Processing Example ===")
    
    # Initialize pipeline
    pipeline = DeepSeaEDNAPipeline()
    
    # Example with paired-end reads
    forward_file = "data/sample_R1.fastq"
    reverse_file = "data/sample_R2.fastq"
    
    if os.path.exists(forward_file) and os.path.exists(reverse_file):
        try:
            # Process paired-end sample
            results = pipeline.process_sample(
                input_files=(forward_file, reverse_file),
                sample_id="deep_sea_paired_001",
                output_dir="results/paired_end"
            )
            
            print(f"Paired-end processing successful: {results['success']}")
            print(f"Input type: {results['input_type']}")
            
        except Exception as e:
            print(f"Paired-end processing failed: {e}")
    else:
        print("Paired-end files not found")
        print("Please provide valid R1 and R2 FASTQ files")


def example_batch_processing():
    """Example: Process multiple samples in batch."""
    print("\n=== Batch Processing Example ===")
    
    # Initialize pipeline
    pipeline = DeepSeaEDNAPipeline()
    
    # Define sample list
    sample_list = [
        {
            "files": "data/sample1_R1.fastq",
            "sample_id": "deep_sea_001"
        },
        {
            "files": ("data/sample2_R1.fastq", "data/sample2_R2.fastq"),
            "sample_id": "deep_sea_002"
        },
        {
            "files": "data/sample3_R1.fastq",
            "sample_id": "deep_sea_003"
        }
    ]
    
    # Filter to only existing files (for demo purposes)
    existing_samples = []
    for sample in sample_list:
        files = sample["files"]
        if isinstance(files, str) and os.path.exists(files):
            existing_samples.append(sample)
        elif isinstance(files, tuple) and all(os.path.exists(f) for f in files):
            existing_samples.append(sample)
    
    if existing_samples:
        try:
            # Process batch
            batch_results = pipeline.process_batch(
                sample_list=existing_samples,
                output_dir="results/batch_processing"
            )
            
            # Print batch summary
            print(f"Batch processing completed:")
            print(f"  Total samples: {batch_results['total_samples']}")
            print(f"  Successful: {batch_results['successful_samples']}")
            print(f"  Failed: {batch_results['failed_samples']}")
            print(f"  Success rate: {batch_results['summary_report']['success_rate']:.1%}")
            print(f"  Total processing time: {batch_results['total_processing_time']:.1f} seconds")
            
            # Show individual sample results
            print("\nIndividual sample results:")
            for sample_id, result in batch_results['sample_results'].items():
                status = "✓" if result.get('success', False) else "✗"
                print(f"  {status} {sample_id}")
            
        except Exception as e:
            print(f"Batch processing failed: {e}")
    else:
        print("No valid sample files found for batch processing")
        print("Please provide valid FASTQ files in the data/ directory")


def example_custom_configuration():
    """Example: Using custom configuration."""
    print("\n=== Custom Configuration Example ===")
    
    # Create custom configuration file path
    config_path = "config/custom_config.yaml"
    
    if os.path.exists(config_path):
        # Initialize pipeline with custom configuration
        pipeline = DeepSeaEDNAPipeline(config_path=config_path)
        print(f"Pipeline initialized with custom config: {config_path}")
        
        # Show some configuration settings
        print("\nCurrent configuration settings:")
        print(f"  Quality threshold: {pipeline.config.get('preprocessing.quality_threshold')}")
        print(f"  Min sequence length: {pipeline.config.get('preprocessing.min_length')}")
        print(f"  Denoise method: {pipeline.config.get('preprocessing.denoise_method')}")
        print(f"  K-mer sizes: {pipeline.config.get('feature_engineering.kmer_size')}")
        print(f"  Normalization method: {pipeline.config.get('abundance.normalization_method')}")
        
    else:
        print(f"Custom config file not found: {config_path}")
        print("Using default configuration")
        pipeline = DeepSeaEDNAPipeline()


def example_pipeline_state():
    """Example: Saving and loading pipeline state."""
    print("\n=== Pipeline State Management Example ===")
    
    # Initialize pipeline
    pipeline = DeepSeaEDNAPipeline()
    
    # Save pipeline state
    state_file = "pipeline_state.json"
    pipeline.save_pipeline_state(state_file)
    print(f"Pipeline state saved to: {state_file}")
    
    # Create new pipeline instance and load state
    new_pipeline = DeepSeaEDNAPipeline()
    if os.path.exists(state_file):
        new_pipeline.load_pipeline_state(state_file)
        print(f"Pipeline state loaded from: {state_file}")
        print(f"Processing history entries: {len(new_pipeline.processing_history)}")
    
    # Clean up
    if os.path.exists(state_file):
        os.remove(state_file)


def create_sample_data():
    """Create sample FASTQ data for testing (if needed)."""
    print("\n=== Creating Sample Data ===")
    
    os.makedirs("data", exist_ok=True)
    
    # Create a minimal sample FASTQ file for testing
    sample_fastq = """@seq1
ATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
+
IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII
@seq2
GCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAG
+
IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII
@seq3  
CCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGGCCGG
+
IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII
"""
    
    sample_file = "data/sample_R1.fastq"
    with open(sample_file, 'w') as f:
        f.write(sample_fastq)
    
    print(f"Sample FASTQ file created: {sample_file}")
    return sample_file


def main():
    """Main function to run examples."""
    print("AI-Driven Deep-Sea eDNA Analysis Pipeline - Usage Examples")
    print("=" * 60)
    
    # Create sample data if needed
    sample_file = create_sample_data()
    
    # Run examples
    try:
        example_single_sample()
        example_custom_configuration()
        example_pipeline_state()
        
        # Note: Paired-end and batch examples would need actual paired files
        print("\nNote: Paired-end and batch examples require actual paired FASTQ files")
        print("Place your files in the data/ directory to test these features")
        
    except Exception as e:
        print(f"Example execution failed: {e}")
    
    finally:
        # Clean up sample data
        if os.path.exists(sample_file):
            os.remove(sample_file)
        if os.path.exists("data") and not os.listdir("data"):
            os.rmdir("data")
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("\nTo use this pipeline with your own data:")
    print("1. Install dependencies: pip install -r requirements.txt")
    print("2. Place FASTQ files in appropriate directory")
    print("3. Modify configuration as needed")
    print("4. Run: python -c 'from edna_pipeline import DeepSeaEDNAPipeline; pipeline = DeepSeaEDNAPipeline(); results = pipeline.process_sample(\"your_file.fastq\")'")


if __name__ == "__main__":
    main()