"""
Taxonomic Assignment Module for eDNA Analysis Pipeline

This module performs taxonomic classification of sequences using various methods
including BLAST searches against reference databases, machine learning models,
and consensus-based approaches.
"""

import os
import re
import shutil
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

from edna_pipeline.feature_engineering.kmer_features import KmerFeatureExtractor

try:
    import joblib
    from sklearn.feature_extraction.text import TfidfTransformer
    from sklearn.metrics import accuracy_score, classification_report, f1_score
    from sklearn.model_selection import train_test_split
    from sklearn.naive_bayes import MultinomialNB
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import LabelEncoder
    from sklearn.svm import SVC
    SKLEARN_IMPORT_ERROR: Optional[ImportError] = None
except ImportError as exc:
    joblib = None
    TfidfTransformer = None
    accuracy_score = None
    classification_report = None
    f1_score = None
    train_test_split = None
    MultinomialNB = None
    Pipeline = None
    LabelEncoder = None
    SVC = None
    SKLEARN_IMPORT_ERROR = exc

# ---------------------------------------------------------------------------
# NCBI taxonomy rank resolution constants
# ---------------------------------------------------------------------------
# Ordered standard ranks recognised by the NCBI taxonomy hierarchy
STANDARD_RANKS = ["superkingdom", "phylum", "class", "order", "family", "genus", "species"]
# Rank aliases: superkingdom is reported as "kingdom" in the output dict
RANK_MAP = {"superkingdom": "kingdom"}
# The NCBI root node always has tax_id == 1 and points to itself
ROOT_TAXID = 1

# Fields present in our BLAST tabular format 6 output (order matters)
BLAST_TABULAR_FIELDS = [
    "qseqid", "sseqid", "pident", "length", "mismatch", "gapopen",
    "qstart", "qend", "sstart", "send", "evalue", "bitscore",
    "staxids", "sscinames", "scomnames", "stitle", "qlen",
]
# The -outfmt string passed to blastn
BLAST_OUTFMT = (
    "6 qseqid sseqid pident length mismatch gapopen qstart qend "
    "sstart send evalue bitscore staxids sscinames scomnames stitle qlen"
)

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


from edna_pipeline.models.classifier import RandomForestKmerClassifier

class TaxonomicAssigner:
    """
    Taxonomic assignment system for eDNA sequences.
    
    Supports multiple classification methods:
    - BLAST-based assignment using reference databases
    - Machine learning models
    - Consensus classification from multiple methods
    """
    
    def __init__(self, database_manager=None, blast_threads: int = 4, config: Optional[Dict] = None):
        """
        Initialize TaxonomicAssigner.
        
        Parameters:
        -----------
        database_manager : DatabaseManager
            Database manager instance
        blast_threads : int
            Number of threads for BLAST searches
        config : Optional[Dict]
            Pipeline configuration. Supports 'kmer_model_path'.
        """
        self.db_manager = database_manager
        self.blast_threads = blast_threads
        self.config = config or {}
        self.logger = logging.getLogger(__name__)

        # ---- NCBI taxonomy caches ----
        # Populated lazily on first call to _get_taxonomy_from_hit()
        # {"nodes": {taxid: {"parent": int, "rank": str}}, "names": {taxid: str}}
        self._taxonomy_cache: Optional[Dict] = None
        # Per-taxid resolved lineage cache — avoids repeated tree traversal
        self._lineage_cache: Dict[int, Dict[str, str]] = {}
        # Path to directory containing nodes.dmp / names.dmp (set below)
        self._taxonomy_dir: Optional[Path] = None

        # Store the taxonomy directory path for lazy loading; do NOT load now.
        if database_manager:
            taxdb_path = database_manager.get_blast_db_path('taxdb')
            if taxdb_path:
                self._taxonomy_dir = Path(taxdb_path)

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

        self.kmer_model_path = Path(self.config.get("kmer_model_path", "models/rf_kmer_classifier.joblib"))
        self.kmer_classifier = RandomForestKmerClassifier(model_path=self.kmer_model_path, k=4)
        if self.kmer_classifier.model is None:
            self.logger.info("No pre-trained k-mer model loaded from %s", self.kmer_model_path)
        
    def load_taxonomy_database(self):
        """No-op: NCBI taxonomy .dmp files are loaded lazily on first hit resolution."""
        pass
    
    def _load_ncbi_taxonomy(self, taxonomy_dir: Path):
        """
        Parse nodes.dmp and names.dmp from an NCBI taxdump directory into
        memory-efficient lookup dicts.

        Populates self._taxonomy_cache:
            {
              "nodes": { tax_id(int): {"parent": int, "rank": str}, ... },
              "names": { tax_id(int): scientific_name(str), ... }
            }

        Parameters
        ----------
        taxonomy_dir : Path
            Directory that contains nodes.dmp and names.dmp.
            Download with: curl -O https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz
        """
        if self._taxonomy_cache is not None:
            return  # Already loaded — honour the lazy-load guarantee

        taxonomy_dir = Path(taxonomy_dir)
        nodes_file = taxonomy_dir / "nodes.dmp"
        names_file = taxonomy_dir / "names.dmp"

        if not nodes_file.exists() or not names_file.exists():
            self.logger.error(
                f"NCBI taxonomy .dmp files not found in '{taxonomy_dir}'. "
                "Download and unpack taxdump.tar.gz from "
                "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz "
                "into that directory."
            )
            # Set empty cache so callers can detect unavailability
            self._taxonomy_cache = {"nodes": {}, "names": {}}
            return

        # ---- Parse nodes.dmp ----
        # Each line: tax_id | parent_tax_id | rank | ... (pipe-delimited, spaces around |)
        nodes: Dict[int, Dict] = {}
        with open(nodes_file, "r", encoding="utf-8") as fh:
            for line in fh:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 3:
                    continue
                tax_id = int(parts[0])
                parent_id = int(parts[1])
                rank = parts[2]
                nodes[tax_id] = {"parent": parent_id, "rank": rank}

        self.logger.info(f"Loaded {len(nodes):,} taxonomy nodes from {nodes_file}")

        # ---- Parse names.dmp ----
        # Each line: tax_id | name_txt | unique_name | name_class
        # Only keep rows where name_class == "scientific name"
        names: Dict[int, str] = {}
        with open(names_file, "r", encoding="utf-8") as fh:
            for line in fh:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 4:
                    continue
                if parts[3] != "scientific name":
                    continue
                tax_id = int(parts[0])
                names[tax_id] = parts[1]

        self.logger.info(f"Loaded {len(names):,} scientific names from {names_file}")

        self._taxonomy_cache = {"nodes": nodes, "names": names}

    def _trigger_lazy_taxonomy_load(self):
        """
        Load taxonomy .dmp files on first use.
        Sets self._taxonomy_cache to an empty dict if files are unavailable.
        """
        if self._taxonomy_cache is not None:
            return

        if self._taxonomy_dir:
            try:
                self._load_ncbi_taxonomy(self._taxonomy_dir)
            except Exception as exc:
                self.logger.warning(f"Could not load NCBI taxonomy: {exc}")
                self._taxonomy_cache = {"nodes": {}, "names": {}}
        else:
            self.logger.debug(
                "No taxonomy directory configured; TaxID resolution will use "
                "taxonkit if available, otherwise return 'Unknown' ranks."
            )
            self._taxonomy_cache = {"nodes": {}, "names": {}}

    def _resolve_taxid_to_lineage(self, taxid: int) -> Dict[str, str]:
        """
        Walk the NCBI taxonomy tree upward from *taxid* to the root, collecting
        the scientific name at each standard rank.

        Algorithm
        ---------
        1. Start at *taxid*.
        2. Follow parent links until reaching ROOT_TAXID (1) or a dead end.
        3. At each node, if its rank is in STANDARD_RANKS, record the name.
        4. "no rank" nodes are traversed transparently — not recorded.
        5. "superkingdom" is remapped to "kingdom" in the output.

        Returns
        -------
        dict with keys: kingdom, phylum, class, order, family, genus, species
        All values default to "Unknown" for ranks absent in the lineage.
        """
        # Build a blank result keyed by output names ("kingdom" instead of "superkingdom")
        result: Dict[str, str] = {RANK_MAP.get(r, r): "Unknown" for r in STANDARD_RANKS}

        if not self._taxonomy_cache:
            return result

        nodes = self._taxonomy_cache["nodes"]
        names = self._taxonomy_cache["names"]

        if taxid not in nodes:
            self.logger.warning(
                f"TaxID {taxid} not found in taxonomy nodes — returning all Unknown"
            )
            return result

        # Walk upward through the tree
        current = taxid
        visited: set = set()  # Guard against any circular references

        while current != ROOT_TAXID:
            if current in visited:
                # Circular reference — should not happen in clean NCBI data
                self.logger.warning(
                    f"Circular parent reference detected at taxid {current}; "
                    "stopping traversal."
                )
                break
            visited.add(current)

            if current not in nodes:
                break  # Dangling node — stop

            node = nodes[current]
            rank = node["rank"]
            parent = node["parent"]

            # Record this node if its rank is one of the seven standard ranks
            if rank in STANDARD_RANKS:
                output_key = RANK_MAP.get(rank, rank)  # "superkingdom" -> "kingdom"
                if result[output_key] == "Unknown":
                    # names.get() returns None when tax_id has no scientific name entry
                    result[output_key] = names.get(current, "Unknown")

            # Move to parent; stop if parent == self (root self-loop)
            if parent == current:
                break
            current = parent

        return result

    def _resolve_taxid_via_taxonkit(self, taxid: int) -> Dict[str, str]:
        """
        Fallback: resolve *taxid* to a lineage dict using the taxonkit CLI.

        Used when nodes.dmp / names.dmp are unavailable but *taxonkit* is on PATH.
        Calls:
            taxonkit lineage --taxid-field 1 --show-rank

        Returns the same dict format as _resolve_taxid_to_lineage():
            {kingdom, phylum, class, order, family, genus, species}
        all defaulting to "Unknown" on any failure.
        """
        result: Dict[str, str] = {RANK_MAP.get(r, r): "Unknown" for r in STANDARD_RANKS}

        try:
            proc = subprocess.run(
                ["taxonkit", "lineage", "--taxid-field", "1", "--show-rank"],
                input=str(taxid),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                self.logger.warning(
                    f"taxonkit returned no output for taxid {taxid}: {proc.stderr.strip()}"
                )
                return result

            # Output: taxid\tlineage\tranks  (one line per input taxid)
            line = proc.stdout.strip().split("\n")[0]
            parts = line.split("\t")
            if len(parts) < 3:
                return result

            lineage_names = [n.strip() for n in parts[1].split(";") if n.strip()]
            lineage_ranks = [r.strip() for r in parts[2].split(";") if r.strip()]

            for rank, name in zip(lineage_ranks, lineage_names):
                if rank in STANDARD_RANKS and name:
                    output_key = RANK_MAP.get(rank, rank)
                    result[output_key] = name

        except subprocess.TimeoutExpired:
            self.logger.warning(f"taxonkit timed out resolving taxid {taxid}")
        except FileNotFoundError:
            self.logger.warning("taxonkit not found on PATH; cannot resolve lineage")
        except Exception as exc:
            self.logger.warning(f"taxonkit fallback failed for taxid {taxid}: {exc}")

        return result

    def _get_taxonomy_from_hit(self, hit: Dict) -> Dict:
        """
        Resolve full 7-rank NCBI taxonomy for a BLAST hit via its staxids field.

        Resolution order:
        1. Check self._lineage_cache (per-taxid, avoids repeated tree traversal).
        2. If nodes.dmp / names.dmp are loaded, call _resolve_taxid_to_lineage().
        3. If .dmp files are absent but taxonkit is on PATH, call
           _resolve_taxid_via_taxonkit().
        4. Otherwise return all "Unknown" ranks.

        Parameters
        ----------
        hit : dict
            A BLAST tabular hit dict keyed by BLAST_TABULAR_FIELDS.

        Returns
        -------
        dict with keys:
            kingdom, phylum, class, order, family, genus, species,
            taxid, pident, evalue, bitscore, stitle, confidence
        """
        # ---- 1. Extract TaxID ----
        # staxids may be comma-separated when a subject sequence is linked to
        # multiple taxa (e.g. artificially merged sequences).  Take the first.
        raw_taxids = str(hit.get("staxids", "0")).strip()
        taxid_str = raw_taxids.split(",")[0].strip()
        try:
            taxid = int(taxid_str) if taxid_str and taxid_str not in ("N/A", "0", "") else 0
        except ValueError:
            taxid = 0

        # ---- 2. Resolve lineage (with caching) ----
        if taxid and taxid in self._lineage_cache:
            # Fast path: already resolved this taxid in a previous hit
            lineage = self._lineage_cache[taxid]
        elif taxid:
            # Lazy-trigger taxonomy load on first use
            if self._taxonomy_cache is None:
                self._trigger_lazy_taxonomy_load()

            nodes_available = bool(self._taxonomy_cache and self._taxonomy_cache.get("nodes"))

            if nodes_available:
                lineage = self._resolve_taxid_to_lineage(taxid)
            elif shutil.which("taxonkit"):
                # Primary dmp files unavailable — use taxonkit CLI as fallback
                lineage = self._resolve_taxid_via_taxonkit(taxid)
            else:
                lineage = {RANK_MAP.get(r, r): "Unknown" for r in STANDARD_RANKS}

            # Cache so subsequent reads hitting the same taxid skip resolution
            self._lineage_cache[taxid] = lineage
        else:
            lineage = {RANK_MAP.get(r, r): "Unknown" for r in STANDARD_RANKS}

        # ---- 3. Assemble result with BLAST metadata ----
        pident = float(hit.get("pident", 0.0))

        result = {
            "kingdom":  lineage.get("kingdom", "Unknown"),
            "phylum":   lineage.get("phylum", "Unknown"),
            "class":    lineage.get("class", "Unknown"),
            "order":    lineage.get("order", "Unknown"),
            "family":   lineage.get("family", "Unknown"),
            "genus":    lineage.get("genus", "Unknown"),
            "species":  lineage.get("species", "Unknown"),
            # BLAST-level metadata
            "taxid":    taxid,
            "pident":   pident,
            "evalue":   float(hit.get("evalue", 1.0)),
            "bitscore": float(hit.get("bitscore", 0.0)),
            "stitle":   hit.get("stitle", ""),
            # ---- 4. Confidence tier ----
            # "high"   : pident >= 97  (typically species-level)
            # "medium" : pident >= 85  (genus/family-level)
            # "low"    : pident <  85  (higher-rank only)
            "confidence": "high" if pident >= 97 else ("medium" if pident >= 85 else "low"),
        }
        return result
    
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
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as result_file:
            result_path = result_file.name
        
        try:
            # Run BLAST with tabular format 6 including staxids for TaxID-based resolution
            blast_cmd = [
                'blastn',
                '-query', query_path,
                '-db', db_path,
                '-out', result_path,
                '-outfmt', BLAST_OUTFMT,
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
            blast_results = self._parse_blast_tabular(result_path)
            
        finally:
            # Clean up temporary files
            os.unlink(query_path)
            os.unlink(result_path)
        
        return blast_results
    
    def _parse_blast_tabular(self, tsv_file: str) -> Dict[str, List[Dict]]:
        """
        Parse BLAST tabular (format 6) output into a dict keyed by query ID.

        Each line is split into BLAST_TABULAR_FIELDS.  Numeric fields are cast
        to float where appropriate.  Returns:
            { query_id: [ {field: value, ...}, ... ], ... }
        """
        results: Dict[str, List[Dict]] = {}

        try:
            with open(tsv_file, 'r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.rstrip('\n')
                    if not line or line.startswith('#'):
                        continue

                    # BLAST tabular lines use a single tab as delimiter
                    cols = line.split('\t')
                    if len(cols) < len(BLAST_TABULAR_FIELDS):
                        # Pad missing columns (e.g. stitle may be absent for some hits)
                        cols += [''] * (len(BLAST_TABULAR_FIELDS) - len(cols))

                    hit = dict(zip(BLAST_TABULAR_FIELDS, cols))

                    # Cast numeric fields
                    for float_field in ('pident', 'evalue', 'bitscore'):
                        try:
                            hit[float_field] = float(hit[float_field])
                        except (ValueError, KeyError):
                            hit[float_field] = 0.0
                    for int_field in ('length', 'mismatch', 'gapopen',
                                      'qstart', 'qend', 'sstart', 'send', 'qlen'):
                        try:
                            hit[int_field] = int(hit[int_field])
                        except (ValueError, KeyError):
                            hit[int_field] = 0

                    # Derived convenience fields used by _calculate_blast_confidence()
                    hit['identity_percent'] = hit['pident']
                    qlen = hit.get('qlen') or 1
                    span = abs(hit.get('qend', 0) - hit.get('qstart', 0)) + 1
                    hit['coverage_percent'] = min(100.0, (span / qlen) * 100.0)

                    query_id = hit['qseqid']
                    results.setdefault(query_id, []).append(hit)

        except Exception as exc:
            self.logger.error(f"Error parsing BLAST tabular output: {exc}")

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
                # Sort hits by e-value (ascending) then identity (descending)
                hits = sorted(all_results[seq_id],
                              key=lambda x: (x['evalue'], -x['identity_percent']))
                best_hit = hits[0]

                # Resolve full taxonomy via TaxID-based tree traversal
                taxonomy = self._get_taxonomy_from_hit(best_hit)

                # Create assignment — map "class" key to TaxonomicAssignment's class_name
                assignment = TaxonomicAssignment(
                    query_id=seq_id,
                    kingdom=taxonomy['kingdom'],
                    phylum=taxonomy['phylum'],
                    class_name=taxonomy['class'],
                    order=taxonomy['order'],
                    family=taxonomy['family'],
                    genus=taxonomy['genus'],
                    species=taxonomy['species'],
                    confidence=self._calculate_blast_confidence(best_hit, hits),
                    method="blast",
                    best_hit_identity=best_hit['identity_percent'],
                    best_hit_coverage=best_hit['coverage_percent'],
                    best_hit_evalue=best_hit['evalue'],
                    best_hit_accession=best_hit.get('sseqid', '')
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
    

    
    def _calculate_blast_confidence(self, best_hit: Dict, all_hits: List[Dict]) -> float:
        """Calculate numeric confidence score (0-100) for a BLAST-based assignment."""
        identity = best_hit.get('identity_percent', best_hit.get('pident', 0.0))
        coverage = best_hit.get('coverage_percent', 100.0)
        evalue = best_hit.get('evalue', 1.0)

        # Base confidence on percent identity
        base_confidence = min(float(identity), 100.0)

        # Penalise low query coverage (< 80 %)
        coverage_factor = min(float(coverage) / 80.0, 1.0)

        # Penalise high e-values
        safe_evalue = max(evalue, 1e-300)  # avoid log(0)
        evalue_factor = max(0.1, min(1.0, -np.log10(safe_evalue) / 10.0))

        # Reduce confidence when multiple high-identity hits exist (ambiguous assignment)
        good_hits = [h for h in all_hits
                     if h.get('identity_percent', h.get('pident', 0.0)) >= 90.0]
        if len(good_hits) > 1:
            diversity_penalty = min(0.2, (len(good_hits) - 1) * 0.05)
            base_confidence *= (1.0 - diversity_penalty)

        confidence = base_confidence * coverage_factor * evalue_factor
        return min(100.0, max(0.0, confidence))
    
    def _kmer_unclassified_result(self) -> Dict[str, Union[str, float, List[Dict[str, float]]]]:
        return {
            "kingdom": "Unclassified",
            "phylum": "Unclassified",
            "class": "Unclassified",
            "order": "Unclassified",
            "family": "Unclassified",
            "genus": "Unclassified",
            "species": "Unclassified",
            "confidence_score": 0.0,
            "confidence_level": "very_low",
            "method": "kmer_ml",
            "model_type": "none",
            "top_3_predictions": [],
        }

    def _prediction_dict_to_assignment(self, query_id: str, prediction: Dict) -> TaxonomicAssignment:
        class_value = prediction.get("class", prediction.get("class_name", "Unknown"))
        confidence_score = float(prediction.get("confidence_score", prediction.get("confidence", 0.0)))
        if confidence_score <= 1.0:
            confidence_score *= 100.0

        return TaxonomicAssignment(
            query_id=query_id,
            kingdom=prediction.get("kingdom", "Unknown"),
            phylum=prediction.get("phylum", "Unknown"),
            class_name=class_value,
            order=prediction.get("order", "Unknown"),
            family=prediction.get("family", "Unknown"),
            genus=prediction.get("genus", "Unknown"),
            species=prediction.get("species", "Unknown"),
            confidence=confidence_score,
            method=prediction.get("method", "kmer_ml"),
        )

    def classify_by_kmer(self, sequences: List[SeqRecord]) -> Dict[str, Dict[str, Union[str, float, List[Dict[str, float]]]]]:
        """
        Classify sequences using a trained k-mer ML model.

        Returns per-sequence prediction dictionaries with keys:
        kingdom, phylum, class, order, family, genus, species,
        confidence_score, confidence_level, method, model_type, top_3_predictions.
        """
        classifications = {}

        model_loaded = (
            self.kmer_classifier is not None
            and self.kmer_classifier.model is not None
            and self.kmer_classifier.label_encoder is not None
        )

        if not model_loaded:
            self.logger.warning(
                "No trained k-mer model found at %s. K-mer classification unavailable. "
                "To train a model, call KmerTaxonomyClassifier.train() with reference sequences.",
                self.kmer_model_path,
            )
            for sequence in sequences:
                classifications[sequence.id] = self._kmer_unclassified_result()
            return classifications

        for sequence in sequences:
            classifications[sequence.id] = self.kmer_classifier.predict(str(sequence.seq))

        return classifications
    
    def consensus_classification(self, classification_results: List[Dict[str, Union[TaxonomicAssignment, Dict]]]) -> Dict[str, TaxonomicAssignment]:
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
            consensus_assignment = self._generate_consensus(assignments, seq_id)
            consensus[seq_id] = consensus_assignment
        
        return consensus
    
    def _generate_consensus(self, assignments: List[Union[TaxonomicAssignment, Dict]], seq_id: str) -> TaxonomicAssignment:
        """Generate consensus from multiple taxonomic assignments."""
        if not assignments:
            return TaxonomicAssignment(query_id=seq_id)

        normalized_assignments = []
        for assignment in assignments:
            if isinstance(assignment, TaxonomicAssignment):
                normalized_assignments.append(assignment)
            elif isinstance(assignment, dict):
                normalized_assignments.append(self._prediction_dict_to_assignment(seq_id, assignment))

        if not normalized_assignments:
            return TaxonomicAssignment(query_id=seq_id)

        if len(normalized_assignments) == 1:
            normalized_assignments[0].method = "consensus"
            return normalized_assignments[0]
        
        # Weight assignments by method and confidence
        weighted_votes = defaultdict(list)
        
        for assignment in normalized_assignments:
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
        best_assignment = max(normalized_assignments, key=lambda x: x.confidence)
        
        return TaxonomicAssignment(
            query_id=normalized_assignments[0].query_id,
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
            consensus_score=len(normalized_assignments)
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
        for query_id, assignment in results.items():
            if isinstance(assignment, dict):
                assignment = self._prediction_dict_to_assignment(query_id, assignment)
            df_data.append(assignment.to_dict())
        
        df = pd.DataFrame(df_data)
        
        # Save as CSV
        df.to_csv(output_file, index=False)
        self.logger.info(f"Results saved to {output_file}")
        
        # Also save as JSON for machine readability
        json_file = output_file.replace('.csv', '.json')
        with open(json_file, 'w') as f:
            json_records = []
            for query_id, assignment in results.items():
                if isinstance(assignment, dict):
                    assignment = self._prediction_dict_to_assignment(query_id, assignment)
                json_records.append(assignment.to_dict())
            json.dump(json_records, f, indent=2)
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
        
        for query_id, assignment in results.items():
            if isinstance(assignment, dict):
                assignment = self._prediction_dict_to_assignment(query_id, assignment)
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