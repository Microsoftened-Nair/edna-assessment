#!/usr/bin/env python3
import sys
from pathlib import Path
import random

# Add project root to python path to allow importing edna_pipeline
sys.path.insert(0, str(Path(__file__).parent.parent))

from edna_pipeline.models.classifier import RandomForestKmerClassifier

def generate_mock_data(num_samples=200):
    # Generates mock DNA sequences and corresponding taxonomic labels
    bases = ['A', 'C', 'G', 'T']
    
    # We will simulate 4 distinct groups (Phyla)
    # Proteobacteria: High GC
    # Cyanobacteria: Moderate GC, specific motifs
    # Bacteroidetes: Low GC
    # Firmicutes: Low GC, AT-rich
    
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
        length = random.randint(150, 300)
        
        if "Proteobacteria" in group:
            weights = [0.15, 0.35, 0.35, 0.15] # High GC
        elif "Cyanobacteria" in group:
            weights = [0.25, 0.25, 0.25, 0.25] # Balanced
        elif "Bacteroidetes" in group:
            weights = [0.35, 0.15, 0.15, 0.35] # Low GC
        else:
            weights = [0.4, 0.1, 0.1, 0.4]     # Very Low GC
            
        for _ in range(length):
            seq.append(random.choices(bases, weights=weights)[0])
            
        # Add a specific motif to make classification more deterministic
        motif = {
            "Proteobacteria": "GGCGCC",
            "Cyanobacteria": "ATCGAT",
            "Bacteroidetes": "AATTAA",
            "Firmicutes": "TTATAA"
        }[group.split(";")[1]]
        
        # Insert motif
        seq_str = "".join(seq)
        insert_pos = random.randint(0, length - len(motif))
        seq_str = seq_str[:insert_pos] + motif + seq_str[insert_pos + len(motif):]
        
        sequences.append(seq_str)
        labels.append(group)
        
    return sequences, labels

def main():
    print("Generating training data...")
    sequences, labels = generate_mock_data(1000)
    
    model_path = Path(__file__).parent.parent / "models" / "rf_kmer_classifier.joblib"
    print(f"Training Random Forest classifier and saving to {model_path}...")
    
    classifier = RandomForestKmerClassifier(k=4)
    # Train
    result = classifier.train(
        sequences=sequences,
        labels=labels,
        model_path=model_path,
        n_estimators=100
    )
    
    print(f"Training complete! Accuracy: {result['accuracy']:.4f}, F1: {result['macro_f1']:.4f}")
    
if __name__ == "__main__":
    main()
