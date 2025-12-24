"""
Taxonomic Assignment Module for eDNA Analysis Pipeline

This module performs taxonomic classification of sequences using various methods
including BLAST searches against reference databases, machine learning models,
and consensus-based approaches.
"""

import os
import sys
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from Bio.Seq import Seq
import json
import pickle
from dataclasses import dataclass
from collections import defaultdict

# Helper lineage mappings for synthetic or custom reference entries to enrich higher ranks
CUSTOM_GENUS_LINEAGE = {
    "Abyssalbacter": {
        "phylum": "Proteobacteria",
        "class_name": "Gammaproteobacteria",
        "order": "Oceanospirillales",
        "family": "Alcanivoracaceae",
    },
    "Hadopelagia": {
        "phylum": "Proteobacteria",
        "class_name": "Alphaproteobacteria",
        "order": "Rhodospirillales",
        "family": "Pelagibacteraceae",
    },
    "Bathycella": {
        "phylum": "Proteobacteria",
        "class_name": "Gammaproteobacteria",
        "order": "Alteromonadales",
        "family": "Alteromonadaceae",
    },
    "Marianobacter": {
        "phylum": "Proteobacteria",
        "class_name": "Gammaproteobacteria",
        "order": "Pseudomonadales",
        "family": "Pseudomonadaceae",
    },
    "Trenchia": {
        "phylum": "Proteobacteria",
        "class_name": "Gammaproteobacteria",
        "order": "Vibrionales",
        "family": "Vibrionaceae",
    },
}

@dataclass
class TaxonomicAssignment:
    """Represents a taxonomic assignment for a sequence."""
    query_id: str
    kingdom: str = "Unknown"
    phylum: str = "Unknown" 
    class_name: str = "Unknown"
    order: str = "Unknown"
    family: str = "Unknown"
    genus: str = "Unknown"
    species: str = "Unknown"
    confidence: float = 0.0
    method: str = "unknown"
    best_hit_identity: float = 0.0
    best_hit_coverage: float = 0.0
    best_hit_evalue: float = float('inf')
    best_hit_accession: str = ""
    consensus_score: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary format."""
        return {
            'query_id': self.query_id,
            'kingdom': self.kingdom,
            'phylum': self.phylum,
            'class': self.class_name,
            'order': self.order,
            'family': self.family,
            'genus': self.genus,
            'species': self.species,
            'confidence': self.confidence,
            'method': self.method,
            'best_hit_identity': self.best_hit_identity,
            'best_hit_coverage': self.best_hit_coverage,
            'best_hit_evalue': self.best_hit_evalue,
            'best_hit_accession': self.best_hit_accession,
            'consensus_score': self.consensus_score
        }

class TaxonomicAssigner:
    """
    Taxonomic assignment system for eDNA sequences.
    
    Supports multiple classification methods:
    - BLAST-based assignment using reference databases
    - Machine learning models
    - Consensus classification from multiple methods
    """
    
    def __init__(self, database_manager=None, blast_threads: int = 4):
        """
        Initialize TaxonomicAssigner.
        
        Parameters:
        -----------
        database_manager : DatabaseManager
            Database manager instance
        blast_threads : int
            Number of threads for BLAST searches
        """
        self.db_manager = database_manager
        self.blast_threads = blast_threads
        self.logger = logging.getLogger(__name__)
        
        # Initialize taxonomy database
        self.taxonomy_db = {}
        self.load_taxonomy_database()
        
        # Classification thresholds
        self.confidence_thresholds = {
            'species': 97.0,
            'genus': 95.0,
            'family': 90.0,
            'order': 85.0,
            'class': 80.0,
            'phylum': 75.0,
            'kingdom': 70.0
        }
        
        # Method weights for consensus classification
        self.method_weights = {
            'blast': 0.4,
            'ml_model': 0.3,
            'kmer': 0.2,
            'phylogenetic': 0.1
        }
        
    def load_taxonomy_database(self):
        """Load NCBI taxonomy database."""
        if self.db_manager:
            taxdb_path = self.db_manager.get_blast_db_path('taxdb')
            if taxdb_path:
                try:
                    # Load taxonomy information
                    self._load_ncbi_taxonomy(taxdb_path)
                except Exception as e:
                    self.logger.warning(f"Could not load NCBI taxonomy: {e}")
    
    def _load_ncbi_taxonomy(self, taxdb_path: str):
        """Load NCBI taxonomy from database files."""
        # This would parse NCBI taxonomy files (nodes.dmp, names.dmp)
        # For now, we'll create a simplified taxonomy structure
        self.taxonomy_db = {
            'tax_id_to_lineage': {},
            'accession_to_taxid': {},
            'name_to_taxid': {}
        }
        self.logger.info("Taxonomy database structure initialized")
    
    def blast_search(self, sequences: List[SeqRecord], database: str = "16S_ribosomal_RNA",
                    max_target_seqs: int = 10, evalue: float = 1e-5) -> Dict[str, List[Dict]]:
        """
        Perform BLAST search against reference database.
        
        Parameters:
        -----------
        sequences : List[SeqRecord]
            Query sequences
        database : str
            Database name to search against
        max_target_seqs : int
            Maximum number of target sequences
        evalue : float
            E-value threshold
            
        Returns:
        --------
        Dict mapping sequence IDs to BLAST hits
        """
        if not self.db_manager:
            self.logger.error("Database manager not available")
            return {}
        
        db_path = self.db_manager.get_blast_db_path(database)
        if not db_path:
            self.logger.error(f"Database {database} not available")
            return {}
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as query_file:
            # Write sequences to temporary file, stripping verbose descriptions that confuse BLAST parsing
            sanitized_records = []
            for record in sequences:
                clean_record = SeqRecord(record.seq, id=record.id, description="")
                sanitized_records.append(clean_record)
            SeqIO.write(sanitized_records, query_file.name, 'fasta')
            query_path = query_file.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as result_file:
            result_path = result_file.name
        
        try:
            # Run BLAST
            blast_cmd = [
                'blastn',
                '-query', query_path,
                '-db', db_path,
                '-out', result_path,
                '-outfmt', '5',  # XML format
                '-max_target_seqs', str(max_target_seqs),
                '-evalue', str(evalue),
                '-num_threads', str(self.blast_threads)
            ]
            
            self.logger.info(f"Running BLAST search against {database}")
            result = subprocess.run(blast_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"BLAST failed: {result.stderr}")
                return {}
            
            # Parse BLAST results
            blast_results = self._parse_blast_xml(result_path)
            
        finally:
            # Clean up temporary files
            os.unlink(query_path)
            os.unlink(result_path)
        
        return blast_results
    
    def _parse_blast_xml(self, xml_file: str) -> Dict[str, List[Dict]]:
        """Parse BLAST XML output."""
        from Bio.Blast import NCBIXML
        
        results = {}
        
        try:
            with open(xml_file, 'r') as f:
                blast_records = NCBIXML.parse(f)
                
                for blast_record in blast_records:
                    query_id = blast_record.query
                    hits = []
                    
                    for alignment in blast_record.alignments:
                        for hsp in alignment.hsps:
                            hit_info = {
                                'accession': alignment.accession,
                                'definition': alignment.hit_def,
                                'length': alignment.length,
                                'evalue': hsp.expect,
                                'identity': hsp.identities,
                                'positives': hsp.positives,
                                'gaps': hsp.gaps,
                                'align_length': hsp.align_length,
                                'query_start': hsp.query_start,
                                'query_end': hsp.query_end,
                                'subject_start': hsp.sbjct_start,
                                'subject_end': hsp.sbjct_end,
                                'identity_percent': (hsp.identities / hsp.align_length) * 100,
                                'coverage_percent': (hsp.align_length / blast_record.query_length) * 100
                            }
                            hits.append(hit_info)
                    
                    results[query_id] = hits
                    
        except Exception as e:
            self.logger.error(f"Error parsing BLAST XML: {e}")
        
        return results
    
    def classify_by_blast(self, sequences: List[SeqRecord], 
                         databases: List[str] = None) -> Dict[str, TaxonomicAssignment]:
        """
        Classify sequences using BLAST against multiple databases.
        
        Parameters:
        -----------
        sequences : List[SeqRecord]
            Sequences to classify
        databases : List[str]
            List of databases to search
            
        Returns:
        --------
        Dict mapping sequence IDs to taxonomic assignments
        """
        if databases is None:
            # Default databases for eDNA analysis
            databases = [
                "16S_ribosomal_RNA",
                "18S_fungal_sequences", 
                "28S_fungal_sequences",
                "ITS_eukaryote_sequences"
            ]
        
        # Remove databases that aren't available
        available_dbs = []
        for db in databases:
            if self.db_manager and self.db_manager.get_blast_db_path(db):
                available_dbs.append(db)
            else:
                self.logger.warning(f"Database {db} not available, skipping")
        
        if not available_dbs:
            self.logger.error("No databases available for BLAST search")
            return {}
        
        # Perform BLAST searches
        all_results = {}
        for database in available_dbs:
            self.logger.info(f"Searching {database}...")
            blast_results = self.blast_search(sequences, database)
            
            for seq_id, hits in blast_results.items():
                if seq_id not in all_results:
                    all_results[seq_id] = []
                all_results[seq_id].extend(hits)
        
        # Classify based on best hits
        classifications = {}
        for sequence in sequences:
            seq_id = sequence.id
            
            if seq_id in all_results and all_results[seq_id]:
                # Sort hits by e-value and identity
                hits = sorted(all_results[seq_id], 
                            key=lambda x: (x['evalue'], -x['identity_percent']))
                best_hit = hits[0]
                
                # Get taxonomic information
                taxonomy = self._get_taxonomy_from_hit(best_hit)
                
                # Create assignment
                assignment = TaxonomicAssignment(
                    query_id=seq_id,
                    **taxonomy,
                    confidence=self._calculate_blast_confidence(best_hit, hits),
                    method="blast",
                    best_hit_identity=best_hit['identity_percent'],
                    best_hit_coverage=best_hit['coverage_percent'],
                    best_hit_evalue=best_hit['evalue'],
                    best_hit_accession=best_hit['accession']
                )
                
                classifications[seq_id] = assignment
            else:
                # No hits found
                classifications[seq_id] = TaxonomicAssignment(
                    query_id=seq_id,
                    method="blast",
                    confidence=0.0
                )
        
        return classifications
    
    def _get_taxonomy_from_hit(self, hit: Dict) -> Dict[str, str]:
        """Extract taxonomic information from BLAST hit."""
        # Parse taxonomic information from hit definition
        # This is a simplified implementation
        raw_definition = hit.get('definition', '')
        definition = raw_definition.lower()
        
        taxonomy = {
            'kingdom': 'Unknown',
            'phylum': 'Unknown',
            'class_name': 'Unknown', 
            'order': 'Unknown',
            'family': 'Unknown',
            'genus': 'Unknown',
            'species': 'Unknown'
        }

        # Attempt to parse semicolon-delimited lineage tokens first
        lineage_tokens = []
        if raw_definition:
            lineage_tokens = [token.strip() for token in raw_definition.split(';') if token.strip()]

        rank_order = ['kingdom', 'phylum', 'class_name', 'order', 'family']
        for idx, token in enumerate(lineage_tokens):
            if idx >= len(rank_order):
                break
            if ' ' in token:
                # Stop before genus/species portion
                continue
            taxonomy[rank_order[idx]] = token

        # Simple pattern matching for common taxa to backfill kingdom if still unknown
        if taxonomy['kingdom'] == 'Unknown':
            if any(word in definition for word in ['bacteria', 'bacterial', 'prokaryot']):
                taxonomy['kingdom'] = 'Bacteria'
            elif any(word in definition for word in ['archaea', 'archaeal']):
                taxonomy['kingdom'] = 'Archaea'
            elif any(word in definition for word in ['eukaryot', 'fungi', 'plant', 'animal']):
                taxonomy['kingdom'] = 'Eukaryota'
                if any(word in definition for word in ['fungi', 'fungal', 'yeast']):
                    taxonomy['kingdom'] = 'Fungi'

        # Extract genus and species if present in standard format
        import re

        lineage_segment = lineage_tokens[-1] if lineage_tokens else raw_definition
        name_pattern = re.compile(r'([A-Za-z][A-Za-z_-]+)\s+([a-z][a-z_-]+)')
        stopwords = {'bacteria', 'archaea', 'virus', 'viruses', 'fungi', 'uncultured', 'metagenome'}

        for match in name_pattern.finditer(lineage_segment):
            genus_token = match.group(1)
            if genus_token.lower() in stopwords:
                continue
            species_token = match.group(2)
            genus = genus_token.capitalize()
            taxonomy['genus'] = genus
            taxonomy['species'] = f"{genus} {species_token.lower()}"
            break

        # Promote higher ranks using custom mapping when available
        genus = taxonomy['genus']
        if genus in CUSTOM_GENUS_LINEAGE:
            for rank, value in CUSTOM_GENUS_LINEAGE[genus].items():
                if taxonomy.get(rank, 'Unknown') == 'Unknown':
                    taxonomy[rank] = value
        
        return taxonomy
    
    def _calculate_blast_confidence(self, best_hit: Dict, all_hits: List[Dict]) -> float:
        """Calculate confidence score for BLAST-based assignment."""
        identity = best_hit['identity_percent']
        coverage = best_hit['coverage_percent']
        evalue = best_hit['evalue']
        
        # Base confidence on identity percentage
        base_confidence = min(identity, 100.0)
        
        # Adjust for coverage
        coverage_factor = min(coverage / 80.0, 1.0)  # Penalty if coverage < 80%
        
        # Adjust for e-value
        evalue_factor = max(0.1, min(1.0, -np.log10(evalue) / 10.0))
        
        # Check for multiple good hits (reduces confidence)
        good_hits = [h for h in all_hits if h['identity_percent'] >= 90.0]
        if len(good_hits) > 1:
            # Reduce confidence if multiple good hits with different taxa
            diversity_penalty = min(0.2, (len(good_hits) - 1) * 0.05)
            base_confidence *= (1.0 - diversity_penalty)
        
        confidence = base_confidence * coverage_factor * evalue_factor
        return min(100.0, max(0.0, confidence))
    
    def classify_by_kmer(self, sequences: List[SeqRecord]) -> Dict[str, TaxonomicAssignment]:
        """
        Classify sequences using k-mer based approach.
        This is a simplified implementation for demonstration.
        """
        classifications = {}
        
        for sequence in sequences:
            # Simplified k-mer classification
            seq_str = str(sequence.seq)
            gc_content = (seq_str.count('G') + seq_str.count('C')) / len(seq_str)
            
            # Very basic heuristic classification based on GC content
            if gc_content < 0.35:
                kingdom = "Bacteria"
                confidence = 30.0
            elif gc_content > 0.65:
                kingdom = "Bacteria"  # Some high-GC bacteria
                confidence = 25.0
            else:
                kingdom = "Unknown"
                confidence = 10.0
            
            assignment = TaxonomicAssignment(
                query_id=sequence.id,
                kingdom=kingdom,
                confidence=confidence,
                method="kmer"
            )
            
            classifications[sequence.id] = assignment
        
        return classifications
    
    def consensus_classification(self, classification_results: List[Dict[str, TaxonomicAssignment]]) -> Dict[str, TaxonomicAssignment]:
        """
        Generate consensus classification from multiple methods.
        
        Parameters:
        -----------
        classification_results : List[Dict]
            List of classification results from different methods
            
        Returns:
        --------
        Dict mapping sequence IDs to consensus assignments
        """
        consensus = {}
        
        # Get all sequence IDs
        all_seq_ids = set()
        for results in classification_results:
            all_seq_ids.update(results.keys())
        
        for seq_id in all_seq_ids:
            # Collect assignments from all methods
            assignments = []
            for results in classification_results:
                if seq_id in results:
                    assignments.append(results[seq_id])
            
            if not assignments:
                continue
            
            # Generate consensus
            consensus_assignment = self._generate_consensus(assignments)
            consensus[seq_id] = consensus_assignment
        
        return consensus
    
    def _generate_consensus(self, assignments: List[TaxonomicAssignment]) -> TaxonomicAssignment:
        """Generate consensus from multiple taxonomic assignments."""
        if not assignments:
            return TaxonomicAssignment(query_id="unknown")
        
        if len(assignments) == 1:
            assignments[0].method = "consensus"
            return assignments[0]
        
        # Weight assignments by method and confidence
        weighted_votes = defaultdict(list)
        
        for assignment in assignments:
            weight = self.method_weights.get(assignment.method, 0.1) * (assignment.confidence / 100.0)
            
            for rank in ['kingdom', 'phylum', 'class_name', 'order', 'family', 'genus', 'species']:
                value = getattr(assignment, rank)
                if value != "Unknown":
                    weighted_votes[rank].append((value, weight))
        
        # Determine consensus for each taxonomic rank
        consensus_taxonomy = {}
        consensus_confidence = 0.0
        
        for rank in ['kingdom', 'phylum', 'class_name', 'order', 'family', 'genus', 'species']:
            if rank in weighted_votes:
                # Calculate weighted votes
                vote_counts = defaultdict(float)
                for value, weight in weighted_votes[rank]:
                    vote_counts[value] += weight
                
                # Select highest weighted vote
                if vote_counts:
                    best_value = max(vote_counts.keys(), key=lambda x: vote_counts[x])
                    total_weight = sum(vote_counts.values())
                    rank_confidence = (vote_counts[best_value] / total_weight) * 100.0
                    
                    consensus_taxonomy[rank] = best_value
                    consensus_confidence += rank_confidence
                else:
                    consensus_taxonomy[rank] = "Unknown"
            else:
                consensus_taxonomy[rank] = "Unknown"
        
        # Average confidence across all ranks
        consensus_confidence /= 7.0
        
        # Use best assignment's additional information
        best_assignment = max(assignments, key=lambda x: x.confidence)
        
        return TaxonomicAssignment(
            query_id=assignments[0].query_id,
            kingdom=consensus_taxonomy['kingdom'],
            phylum=consensus_taxonomy['phylum'],
            class_name=consensus_taxonomy['class_name'],
            order=consensus_taxonomy['order'],
            family=consensus_taxonomy['family'],
            genus=consensus_taxonomy['genus'],
            species=consensus_taxonomy['species'],
            confidence=consensus_confidence,
            method="consensus",
            best_hit_identity=best_assignment.best_hit_identity,
            best_hit_coverage=best_assignment.best_hit_coverage,
            best_hit_evalue=best_assignment.best_hit_evalue,
            best_hit_accession=best_assignment.best_hit_accession,
            consensus_score=len(assignments)
        )
    
    def assign_taxonomy(self, sequences: List[SeqRecord], methods: List[str] = None) -> Dict[str, TaxonomicAssignment]:
        """
        Assign taxonomy using multiple methods and generate consensus.
        
        Parameters:
        -----------
        sequences : List[SeqRecord]
            Sequences to classify
        methods : List[str]
            Methods to use ('blast', 'kmer', 'ml')
            
        Returns:
        --------
        Dict mapping sequence IDs to final taxonomic assignments
        """
        if methods is None:
            methods = ['blast', 'kmer']
        
        self.logger.info(f"Starting taxonomic assignment using methods: {methods}")
        
        all_results = []
        
        # BLAST-based classification
        if 'blast' in methods:
            self.logger.info("Running BLAST-based classification...")
            blast_results = self.classify_by_blast(sequences)
            if blast_results:
                all_results.append(blast_results)
        
        # K-mer based classification  
        if 'kmer' in methods:
            self.logger.info("Running k-mer based classification...")
            kmer_results = self.classify_by_kmer(sequences)
            if kmer_results:
                all_results.append(kmer_results)
        
        # Generate consensus if multiple methods used
        if len(all_results) > 1:
            self.logger.info("Generating consensus classification...")
            final_results = self.consensus_classification(all_results)
        elif len(all_results) == 1:
            final_results = all_results[0]
        else:
            self.logger.error("No classification results obtained")
            final_results = {}
        
        self.logger.info(f"Taxonomic assignment completed for {len(final_results)} sequences")
        return final_results
    
    def save_results(self, results: Dict[str, TaxonomicAssignment], output_file: str):
        """Save taxonomic assignment results to file."""
        # Convert to pandas DataFrame
        df_data = []
        for assignment in results.values():
            df_data.append(assignment.to_dict())
        
        df = pd.DataFrame(df_data)
        
        # Save as CSV
        df.to_csv(output_file, index=False)
        self.logger.info(f"Results saved to {output_file}")
        
        # Also save as JSON for machine readability
        json_file = output_file.replace('.csv', '.json')
        with open(json_file, 'w') as f:
            json.dump([assignment.to_dict() for assignment in results.values()], f, indent=2)
        self.logger.info(f"Results also saved to {json_file}")
    
    def generate_summary_report(self, results: Dict[str, TaxonomicAssignment]) -> Dict:
        """Generate summary statistics from taxonomic assignments."""
        if not results:
            return {}
        
        # Count assignments at each taxonomic level
        level_counts = {}
        for level in ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']:
            level_counts[level] = {}
            
        total_sequences = len(results)
        confidence_scores = []
        
        for assignment in results.values():
            confidence_scores.append(assignment.confidence)
            
            for level in ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']:
                value = getattr(assignment, level if level != 'class' else 'class_name')
                if value != "Unknown":
                    level_counts[level][value] = level_counts[level].get(value, 0) + 1
        
        summary = {
            'total_sequences': total_sequences,
            'mean_confidence': np.mean(confidence_scores) if confidence_scores else 0.0,
            'median_confidence': np.median(confidence_scores) if confidence_scores else 0.0,
            'taxonomic_diversity': level_counts,
            'classification_success_rates': {}
        }
        
        # Calculate success rates at each level
        for level, counts in level_counts.items():
            classified = sum(counts.values())
            success_rate = (classified / total_sequences) * 100.0
            summary['classification_success_rates'][level] = success_rate
        
        return summary