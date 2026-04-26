#!/usr/bin/env python3
"""Train a supervised embedding-based taxonomy classifier.

This script takes a labeled FASTA file (e.g., from SILVA, PR2, NCBI), 
generates DNABERT-2 embeddings for the sequences, and trains a downstream 
classifier (Random Forest or K-Nearest Neighbors) to map those embeddings 
to actual taxonomic labels.

The output `model_bundle.joblib` can then be passed to the eDNA pipeline 
to replace the default unsupervised OTU-1, OTU-2 taxonomic assignments 
with actual species classifications.
"""

import sys
import argparse
from pathlib import Path
import random
import time

# Add project root to python path to allow importing edna_pipeline
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import joblib
import numpy as np
from Bio import SeqIO
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from edna_pipeline.models.dnabert2_classifier import DNABERT2EmbeddingsExtractor

def generate_mock_data(num_samples=200):
    """Generates mock DNA sequences and corresponding taxonomic labels."""
    bases = ['A', 'C', 'G', 'T']
    
    labels = []
    sequences = []
    
    for _ in range(num_samples):
        group = random.choice([
            "Bacteria;Proteobacteria;Gammaproteobacteria;Oceanospirillales;Alcanivoracaceae;Abyssalbacter;marinus",
            "Bacteria;Cyanobacteria;Oxyphotobacteria;Synechococcales;Synechococcaceae;Synechococcus;sp.",
            "Bacteria;Bacteroidetes;Bacteroidia;Bacteroidales;Bacteroidaceae;Bacteroides;fragilis",
            "Bacteria;Firmicutes;Bacilli;Bacillales;Bacillaceae;Bacillus;subtilis"
        ])
        
        # Sequence generation based on group
        seq = []
        length = random.randint(150, 200)
        
        if "Proteobacteria" in group:
            weights = [0.15, 0.35, 0.35, 0.15]
        elif "Cyanobacteria" in group:
            weights = [0.25, 0.25, 0.25, 0.25]
        elif "Bacteroidetes" in group:
            weights = [0.35, 0.15, 0.15, 0.35]
        else:
            weights = [0.4, 0.1, 0.1, 0.4]
            
        for _ in range(length):
            seq.append(random.choices(bases, weights=weights)[0])
            
        # Add a specific motif to make classification more deterministic
        motif = {
            "Proteobacteria": "GGCGCC",
            "Cyanobacteria": "ATCGAT",
            "Bacteroidetes": "AATTAA",
            "Firmicutes": "TTATAA"
        }[group.split(";")[1]]
        
        seq_str = "".join(seq)
        insert_pos = random.randint(0, length - len(motif))
        seq_str = seq_str[:insert_pos] + motif + seq_str[insert_pos + len(motif):]
        
        sequences.append(seq_str)
        labels.append(group)
        
    return sequences, labels

def main():
    parser = argparse.ArgumentParser(description="Train an embedding taxonomy classifier.")
    parser.add_argument("--fasta", help="Path to labeled FASTA file. Labels should be in the header/description separated by semicolons.")
    parser.add_argument("--output", default="models/embedding_model_bundle.joblib", help="Output joblib model bundle path")
    parser.add_argument("--samples", type=int, default=100, help="Number of mock samples if no FASTA is provided")
    parser.add_argument("--max-train-samples", type=int, default=3000, help="Limit number of samples to train on (to speed up compute)")
    args = parser.parse_args()
    
    if args.fasta:
        print(f"Loading sequences and labels from {args.fasta}...")
        sequences = []
        labels = []
        # Parse the fasta file
        for record in SeqIO.parse(args.fasta, "fasta"):
            sequences.append(str(record.seq))
            # Assume the header description contains the taxonomy string
            # Handle tab-separated (mothur format) or space separated headers
            desc = record.description
            if "\t" in desc:
                label = desc.split("\t", 1)[1].strip()
            elif " " in desc:
                label = desc.split(" ", 1)[1].strip()
            else:
                label = desc.strip()
            labels.append(label)
            
            # Limit the number of samples to process if specified, generating embeddings is slow
            if args.max_train_samples > 0 and len(sequences) >= args.max_train_samples:
                print(f"Reached max training samples limit ({args.max_train_samples}). Subsampling finished.")
                break
    else:
        print("No FASTA provided. Generating mock reference database...")
        sequences, labels = generate_mock_data(args.samples)
        
    print(f"Found {len(sequences)} sequences for training.")
        
    print("Generating DNABERT-2 embeddings (this might take a while)...")
    start_time = time.time()
    extractor = DNABERT2EmbeddingsExtractor(
        model_name="zhihan1996/DNABERT-2-117M",
        max_length=256,
        device=None, # auto detect
    )
    embeddings = extractor.extract(sequences, batch_size=16)
    print(f"Embeddings generated in {time.time() - start_time:.2f} seconds.")
    
    print("Encoding labels...")
    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(labels)
    
    print("Training Random Forest Classifier on Embeddings...")
    # Wrap in standard scaler to improve robustness
    classifier = make_pipeline(StandardScaler(), RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1))
    classifier.fit(embeddings, y_encoded)
    
    # Evaluate on train data just as a sanity check
    train_acc = classifier.score(embeddings, y_encoded)
    print(f"Training accuracy: {train_acc:.4f}")
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save the bundle format that `EmbeddingTaxonomyClassifier` expects
    bundle = {
        "classifier": classifier,
        "label_encoder": label_encoder,
        "taxonomy_by_label": {} # Optional mapping if labels aren't strings
    }
    
    joblib.dump(bundle, str(output_path))
    print(f"✅ Successfully saved embedding model bundle to: {output_path}")
    print("\nTo use this model for actual species classifications, update your API request or server config:")
    print('  "configOverrides": {')
    print('      "classification.model_bundle": "models/embedding_model_bundle.joblib"')
    print('  }')

if __name__ == "__main__":
    main()
