# AI-Driven Deep-Sea eDNA Analysis Pipeline for Eukaryotic Biodiversity Assessment

## Project Overview

This project implements an innovative bioinformatics pipeline that uses artificial intelligence and machine learning to analyze environmental DNA (eDNA) from deep-sea ecosystems. The pipeline addresses the challenge of accurately identifying novel or poorly-represented deep-sea eukaryotic organisms by minimizing reliance on incomplete reference databases.

## Key Features

- **AI-Powered Classification**: Deep learning models (CNNs, LSTMs, Transformers) for sequence pattern recognition
- **Novel Taxa Discovery**: Unsupervised clustering to identify potentially new species
- **Hierarchical Taxonomy**: Multi-level taxonomic classification with confidence scores
- **Computational Efficiency**: GPU acceleration and parallel processing
- **Comprehensive Analysis**: Abundance estimation, diversity metrics, and biodiversity assessment

## Target Applications

- **Markers**: 18S rRNA and COI gene sequences
- **Organisms**: Protists, Cnidarians, rare metazoans, novel deep-sea eukaryotes
- **Ecosystems**: Deep-sea water and sediment samples

## Installation

### Prerequisites

- Python 3.8 or higher
- BLAST+ (for taxonomic assignment)
- At least 5GB free disk space for recommended databases

### Installation Steps

```bash
# Clone the repository
git clone https://github.com/your-repo/deep-sea-edna-pipeline.git
cd deep-sea-edna-pipeline

# Create conda environment
conda create -n edna-pipeline python=3.9
conda activate edna-pipeline

# Install BLAST+ (required for taxonomic classification)
conda install -c bioconda blast

# Install Python dependencies
pip install -r requirements.txt

# Set up reference databases
python setup_databases.py --recommended
```

## Quick Start

### 1. Set up Reference Databases

First, download the required reference databases from NCBI:

```bash
# Download recommended databases for eDNA analysis (~400MB)
python setup_databases.py --recommended

# Or download specific databases
python setup_databases.py --databases taxdb 16S_ribosomal_RNA ITS_eukaryote_sequences

# List available databases
python setup_databases.py --list
```

### 2. Run the Pipeline

```python
from edna_pipeline import DeepSeaEDNAPipeline

# Initialize pipeline with database directory
pipeline = DeepSeaEDNAPipeline(db_dir="databases")

# Process a single sample
results = pipeline.process_sample(
    input_files="path/to/sample.fastq",  # or ("R1.fastq", "R2.fastq") for paired-end
    sample_id="my_sample",
    output_dir="results"
)

# Check results
if results["success"]:
    print(f"Processing completed successfully!")
    classification_step = next(s for s in results["pipeline_steps"] if s["step"] == "taxonomic_classification")
    print(f"Classified ASVs: {classification_step['results']['total_classified']}")
    print(f"Mean confidence: {classification_step['results']['mean_confidence']:.2f}%")
else:
    print(f"Processing failed: {results['error']}")
```

### 3. Quick Test with Sample Data

```bash
# Generate and analyze sample data
python example_usage.py --create-sample 20 --output-dir test_results
```

## Pipeline Architecture

1. **Data Preprocessing**: Quality filtering, adapter trimming, chimera detection
2. **Feature Engineering**: k-mer extraction, sequence embeddings, composition analysis
3. **AI Model Application**: 
   - Supervised classification for known taxa
   - Unsupervised clustering for novel taxa discovery
4. **Taxonomic Assignment**: Confidence scoring and hierarchical taxonomy
5. **Abundance Quantification**: Normalized read counts and diversity metrics
6. **Visualization & Reporting**: Interactive dashboards and biodiversity reports

## Key Capabilities

### Machine Learning Models
- Convolutional Neural Networks for local sequence patterns
- LSTM/GRU networks for sequential dependencies
- Transformer models for long-range relationships
- Ensemble methods combining multiple architectures

### Novel Taxa Discovery
- Deep autoencoders for feature learning
- HDBSCAN/DBSCAN clustering
- Outlier detection for divergent sequences
- Phylogenetic placement analysis

### Biodiversity Assessment
- Shannon, Simpson, Chao1 diversity indices
- Rarefaction curve analysis
- Beta diversity comparisons
- Community composition visualization

## Directory Structure

```
deep-sea-edna-pipeline/
├── edna_pipeline/              # Main package
│   ├── preprocessing/          # Data preprocessing modules
│   ├── feature_engineering/    # Feature extraction and engineering
│   ├── models/                # ML/DL model implementations
│   ├── taxonomy/              # Taxonomic assignment and annotation
│   ├── abundance/             # Abundance quantification
│   ├── visualization/         # Plotting and reporting
│   └── utils/                 # Utility functions
├── config/                    # Configuration files
├── data/                      # Sample data and databases
├── tests/                     # Unit and integration tests
├── docs/                      # Documentation
├── scripts/                   # Example scripts and workflows
└── requirements.txt           # Python dependencies
```

## Dependencies

- **Deep Learning**: TensorFlow/PyTorch, Keras
- **Bioinformatics**: BioPython, VSEARCH
- **Data Processing**: NumPy, Pandas, Polars, Dask
- **Machine Learning**: Scikit-learn, UMAP, HDBSCAN
- **Visualization**: Matplotlib, Seaborn, Plotly
- **Ecology**: Scikit-bio

## Contributing

Please read CONTRIBUTING.md for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Citation

If you use this pipeline in your research, please cite:
```
[Citation information will be added upon publication]
```

## Support

For questions and support, please open an issue on GitHub or contact the development team.