# eDNA Analysis Pipeline - Complete Usage Guide

## Overview

This enhanced eDNA analysis pipeline now includes integrated database management and taxonomic assignment using NCBI reference databases. The pipeline can automatically download and manage reference databases, perform BLAST searches, and provide accurate taxonomic classifications with confidence scores.

## System Requirements

- **Python**: 3.8 or higher
- **BLAST+**: Required for taxonomic classification
- **Disk Space**: At least 5GB recommended; optional comprehensive sets can exceed 700GB
- **Memory**: Recommended 8GB RAM or higher
- **Internet**: Required for database downloads

## Installation and Setup

### 1. Install Prerequisites

```bash
# Install BLAST+ (choose one method)
conda install -c bioconda blast        # Using conda (recommended)
# OR
sudo apt-get install ncbi-blast+       # Ubuntu/Debian
# OR  
brew install blast                     # macOS
```

### 2. Set Up Python Environment

```bash
# Create and activate environment
python -m venv virt
source virt/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 3. Download Reference Databases

The pipeline uses several NCBI databases for accurate taxonomic classification:

#### Quick Setup (Recommended for Most Users)
```bash
# Downloads essential databases (~400MB total)
python setup_databases.py --recommended
```

This downloads:
- **taxdb** (~70MB): NCBI taxonomy dump (setup extracts `nodes.dmp` and `names.dmp`) - *Required for full lineage resolution*
- **16S_ribosomal_RNA** (65MB): 16S rRNA sequences for prokaryotes
- **18S_fungal_sequences** (58MB): 18S rRNA sequences for fungi
- **28S_fungal_sequences** (60MB): 28S rRNA sequences for fungi
- **ITS_eukaryote_sequences** (71MB): ITS sequences for eukaryotes
- **ITS_RefSeq_Fungi** (61MB): RefSeq fungal ITS sequences

Important: processing does not auto-download databases during `process_sample`. If a required database is missing, BLAST-based assignment for that database is skipped.

#### Advanced Setup Options

```bash
# List all available databases
python setup_databases.py --list

# Download specific databases
python setup_databases.py --databases taxdb 16S_ribosomal_RNA

# Download for comprehensive analysis (WARNING: ~200GB)
python setup_databases.py --databases core_nt

# Download for complete analysis (WARNING: ~600GB)
python setup_databases.py --databases nt

# Download eukaryote-focused comprehensive set (WARNING: ~570GB)
python setup_databases.py --databases nt_euk
```

## Usage Examples

### 1. Basic Single Sample Analysis

```python
from edna_pipeline import DeepSeaEDNAPipeline

# Initialize pipeline
pipeline = DeepSeaEDNAPipeline(db_dir="databases")

# Process single-end reads
results = pipeline.process_sample(
    input_files="sample.fastq",
    sample_id="sample_001",
    output_dir="results"
)

# Check results
if results["success"]:
    print(f"✅ Processing completed successfully!")
    
    # Get classification results
    classification_step = next(s for s in results["pipeline_steps"] 
                             if s["step"] == "taxonomic_classification")
    
    print(f"📊 Classification Summary:")
    print(f"  - Total ASVs: {len(results['pipeline_steps'][0]['results']['abundance_table'])}")
    print(f"  - Classified ASVs: {classification_step['results']['total_classified']}")
    print(f"  - Mean confidence: {classification_step['results']['mean_confidence']:.1f}%")
    print(f"  - Method: {classification_step['results']['classification_method']}")
    
    # Get diversity metrics
    abundance_step = next(s for s in results["pipeline_steps"] 
                         if s["step"] == "abundance_quantification")
    
    diversity = abundance_step['results']['diversity_metrics']
    for sample_name, metrics in diversity.items():
        print(f"🌍 Diversity Metrics for {sample_name}:")
        for metric, value in metrics.items():
            print(f"  - {metric.capitalize()}: {value:.3f}")
else:
    print(f"❌ Processing failed: {results['error']}")
```

### 2. Paired-End Sample Analysis

```python
# Process paired-end reads
results = pipeline.process_sample(
    input_files=("sample_R1.fastq", "sample_R2.fastq"),
    sample_id="sample_002", 
    output_dir="results"
)
```

### 3. Batch Processing Multiple Samples

```python
# Define sample list
sample_list = [
    {"files": "sample1.fastq", "sample_id": "sample_001"},
    {"files": ("sample2_R1.fastq", "sample2_R2.fastq"), "sample_id": "sample_002"},
    {"files": "sample3.fastq", "sample_id": "sample_003"},
]

# Process batch
batch_results = pipeline.process_batch(sample_list, output_dir="batch_results")

print(f"Batch processing: {batch_results['successful_samples']}/{batch_results['total_samples']} successful")
```

### 4. Using the Command Line Interface

```bash
# Test with generated sample data
python example_usage.py --create-sample 50 --output-dir test_results

# Analyze your own data
python example_usage.py --input your_sample.fastq --output-dir results

# Verbose output for debugging
python example_usage.py --input your_sample.fastq --verbose
```

### 5. Database Management

```bash
# Check database status
python setup_databases.py --list

# Download additional databases
python setup_databases.py --databases nt_euk

# Clean up downloaded files to save space (keeps processed databases)
python -c "
from edna_pipeline.database_manager import DatabaseManager
db = DatabaseManager('databases')
db.cleanup_downloads(keep_processed=True)
"
```

## Output Files

Each sample analysis produces several output files:

### Preprocessing Outputs
- `{sample_id}/processed_reads.fastq`: Quality-filtered reads
- `{sample_id}/asvs.fasta`: Amplicon Sequence Variants (ASVs)
- `{sample_id}/abundance_table.tsv`: ASV abundance counts

### Feature Analysis Outputs
- `{sample_id}/features.pkl`: Extracted sequence features
- `{sample_id}/feature_statistics.txt`: Feature summary statistics

### Taxonomic Classification Outputs
- `{sample_id}/taxonomic_assignments.csv`: Detailed taxonomic assignments with confidence scores
- `{sample_id}/taxonomic_assignments.json`: Machine-readable format
- `{sample_id}/taxonomy.json`: Legacy format for compatibility
- `{sample_id}/taxonomy_summary.json`: Classification summary statistics

### Abundance and Diversity Outputs  
- `{sample_id}/abundance_matrix.csv`: Raw abundance matrix
- `{sample_id}/normalized_abundance.csv`: Normalized abundance values
- `{sample_id}/diversity_metrics.csv`: Alpha diversity indices
- `{sample_id}/taxonomic_abundance.json`: Abundance aggregated by taxonomic level

### Reports
- `{sample_id}/sample_report.html`: Interactive HTML report
- `{sample_id}/pipeline_results.json`: Complete pipeline results

## Configuration

The pipeline can be customized using a YAML configuration file:

```yaml
taxonomy:
  methods: ["blast", "kmer"]  # Classification methods
  databases: ["16S_ribosomal_RNA", "ITS_eukaryote_sequences"]  # Databases to search
  confidence_threshold: 0.7  # Minimum confidence for classification
  blast_evalue: 1e-5         # BLAST E-value threshold

preprocessing:
  quality_threshold: 20      # Minimum quality score
  min_length: 100           # Minimum sequence length
  max_length: 2000          # Maximum sequence length

computing:
  blast_threads: 4          # Number of BLAST threads
  n_jobs: -1               # Parallel processing jobs
```

## Troubleshooting

### Database Issues

**Problem**: "Database not available" errors
```bash
# Check database status
python setup_databases.py --list

# Re-download missing databases
python setup_databases.py --recommended

# Or fetch a specific missing one
python setup_databases.py --databases taxdb ITS_eukaryote_sequences
```

**Problem**: Download failures
```bash
# Retry individual databases
python setup_databases.py --databases taxdb --verbose

# Check internet connection and disk space
df -h .
```

### BLAST Issues

**Problem**: "blastn command not found"
```bash
# Install BLAST+
conda install -c bioconda blast

# Verify installation
blastn -version
```

**Problem**: BLAST searches failing
```bash
# Check if databases are properly extracted
ls databases/processed/*/

# Test BLAST manually
blastn -db databases/processed/16S_ribosomal_RNA/16S_ribosomal_RNA -query test.fasta -outfmt 6
```

### Memory Issues

**Problem**: Out of memory errors
- Reduce `blast_threads` in configuration
- Process samples individually instead of in batch
- Use smaller databases (avoid `nt` and `core_nt`)

### Performance Optimization

**For faster processing**:
- Increase `blast_threads` (up to number of CPU cores)
- Use SSD storage for databases
- Enable `n_jobs: -1` for parallel processing

**For lower memory usage**:
- Set `blast_threads: 1`
- Use `--no-extract` when downloading databases
- Process samples sequentially

## Support and Further Information

- **Documentation**: See `docs/` directory for detailed API documentation
- **Examples**: Check `scripts/` directory for more usage examples  
- **Issues**: Report bugs and request features on GitHub
- **Performance**: See `PERFORMANCE.md` for optimization guidelines

## Database Information

### Recommended Databases (Essential)
- **taxdb**: NCBI taxonomy mapping - Required for all analyses
- **16S_ribosomal_RNA**: Prokaryotic identification (Bacteria, Archaea)
- **18S_fungal_sequences**: Fungal identification
- **28S_fungal_sequences**: Additional fungal markers
- **ITS_eukaryote_sequences**: Eukaryotic identification
- **ITS_RefSeq_Fungi**: High-quality fungal sequences

### Optional Databases (Advanced)
- **nt_euk**: Eukaryotic nucleotide sequences (~150GB)
- **core_nt**: Core nucleotide database (~200GB) 
- **nt**: Complete nucleotide database (~600GB)
- **refseq_rna**: RefSeq RNA sequences (~50GB)

### Database Selection Guide

**Marine/Freshwater eDNA**: Use recommended databases + `nt_euk` if space allows

**Soil eDNA**: Add fungal databases (`18S_fungal_sequences`, `28S_fungal_sequences`)

**Comprehensive Analysis**: Use `core_nt` or `nt` (requires significant storage and time)

**Quick Testing**: Use only `taxdb` + `16S_ribosomal_RNA`
