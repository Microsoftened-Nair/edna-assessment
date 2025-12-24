"""
Database Manager Module for eDNA Analysis Pipeline

This module handles downloading, managing, and updating reference databases
from NCBI and other sources for taxonomic classification.
"""

import os
import sys
import logging
import requests
import hashlib
import tarfile
import gzip
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin
import time

class DatabaseManager:
    """
    Manages reference databases for eDNA taxonomic classification.
    
    Supports downloading and managing NCBI BLAST databases including:
    - nt (nucleotide): Complete nucleotide database
    - core_nt: Core nucleotide database (smaller)
    - 16S_ribosomal_RNA: 16S rRNA sequences
    - 18S_fungal_sequences: 18S fungal sequences
    - 28S_fungal_sequences: 28S fungal sequences
    - ITS_eukaryote_sequences: ITS sequences for eukaryotes
    - nt_euk: Eukaryotic nucleotide sequences
    - ref_euk_rep_genomes: Reference eukaryotic genomes
    - taxdb: Taxonomy database
    """
    
    # NCBI FTP base URL
    NCBI_FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/blast/db/"
    
    # Available databases relevant for eDNA analysis
    AVAILABLE_DATABASES = {
        "nt": {
            "description": "Complete NCBI nucleotide database (large ~600GB)",
            "files": "nt.*.tar.gz",
            "priority": "low",  # Very large
            "use_case": "comprehensive_analysis"
        },
        "core_nt": {
            "description": "Core nucleotide database (medium ~200GB)",
            "files": "core_nt.*.tar.gz", 
            "priority": "medium",
            "use_case": "balanced_analysis"
        },
        "16S_ribosomal_RNA": {
            "description": "16S ribosomal RNA sequences for prokaryotes",
            "files": "16S_ribosomal_RNA.tar.gz",
            "priority": "high",
            "use_case": "prokaryote_identification"
        },
        "18S_fungal_sequences": {
            "description": "18S rRNA sequences for fungi", 
            "files": "18S_fungal_sequences.tar.gz",
            "priority": "high",
            "use_case": "fungal_identification"
        },
        "28S_fungal_sequences": {
            "description": "28S rRNA sequences for fungi",
            "files": "28S_fungal_sequences.tar.gz", 
            "priority": "high",
            "use_case": "fungal_identification"
        },
        "ITS_eukaryote_sequences": {
            "description": "ITS sequences for eukaryotes",
            "files": "ITS_eukaryote_sequences.tar.gz",
            "priority": "high", 
            "use_case": "eukaryote_identification"
        },
        "ITS_RefSeq_Fungi": {
            "description": "RefSeq fungal ITS sequences",
            "files": "ITS_RefSeq_Fungi.tar.gz",
            "priority": "high",
            "use_case": "fungal_identification"  
        },
        "nt_euk": {
            "description": "Eukaryotic nucleotide sequences",
            "files": "nt_euk.*.tar.gz",
            "priority": "medium",
            "use_case": "eukaryote_analysis"
        },
        "ref_euk_rep_genomes": {
            "description": "Reference eukaryotic representative genomes",
            "files": "ref_euk_rep_genomes.*.tar.gz", 
            "priority": "low",  # Very large
            "use_case": "genome_level_analysis"
        },
        "taxdb": {
            "description": "NCBI taxonomy database",
            "files": "taxdb.tar.gz",
            "priority": "critical",
            "use_case": "taxonomy_mapping"
        },
        "refseq_rna": {
            "description": "RefSeq RNA sequences",
            "files": "refseq_rna.*.tar.gz",
            "priority": "medium", 
            "use_case": "rna_analysis"
        }
    }
    
    def __init__(self, db_dir: str = "databases", max_concurrent_downloads: int = 3):
        """
        Initialize DatabaseManager.
        
        Parameters:
        -----------
        db_dir : str
            Directory to store databases
        max_concurrent_downloads : int
            Maximum concurrent downloads
        """
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent_downloads
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Create subdirectories
        (self.db_dir / "raw").mkdir(exist_ok=True)
        (self.db_dir / "processed").mkdir(exist_ok=True) 
        (self.db_dir / "logs").mkdir(exist_ok=True)
        
        # Track database status
        self.db_status_file = self.db_dir / "database_status.json"
        self.load_database_status()
        
    def load_database_status(self):
        """Load database download and processing status."""
        import json
        
        if self.db_status_file.exists():
            try:
                with open(self.db_status_file, 'r') as f:
                    self.db_status = json.load(f)
            except Exception as e:
                self.logger.warning(f"Could not load database status: {e}")
                self.db_status = {}
        else:
            self.db_status = {}
            
    def save_database_status(self):
        """Save database status to file."""
        import json
        
        try:
            with open(self.db_status_file, 'w') as f:
                json.dump(self.db_status, f, indent=2)
        except Exception as e:
            self.logger.error(f"Could not save database status: {e}")
    
    def get_available_files(self) -> Dict[str, List[str]]:
        """
        Get list of available files for each database from NCBI FTP.
        
        Returns:
        --------
        Dict mapping database names to list of available files
        """
        available_files = {}
        
        try:
            # Get directory listing from NCBI FTP
            response = requests.get(self.NCBI_FTP_BASE, timeout=30)
            response.raise_for_status()
            
            # Parse HTML to extract file names
            import re
            file_pattern = re.compile(r'href="([^"]+\.tar\.gz)"')
            all_files = file_pattern.findall(response.text)
            
            # Match files to databases
            for db_name, db_info in self.AVAILABLE_DATABASES.items():
                pattern = db_info["files"]
                if "*" in pattern:
                    # Handle wildcard patterns
                    prefix = pattern.split("*")[0]
                    suffix = pattern.split("*")[1]
                    matching_files = [f for f in all_files 
                                    if f.startswith(prefix) and f.endswith(suffix)]
                else:
                    # Exact match
                    matching_files = [f for f in all_files if f == pattern]
                
                available_files[db_name] = matching_files
                
        except Exception as e:
            self.logger.error(f"Failed to get available files: {e}")
            return {}
            
        return available_files
    
    def download_file(self, filename: str, destination: Path, 
                     verify_checksum: bool = True) -> bool:
        """
        Download a single file from NCBI FTP.
        
        Parameters:
        -----------
        filename : str
            Name of file to download
        destination : Path  
            Local destination path
        verify_checksum : bool
            Whether to verify MD5 checksum
            
        Returns:
        --------
        bool: Success status
        """
        url = urljoin(self.NCBI_FTP_BASE, filename)
        
        try:
            self.logger.info(f"Downloading {filename}...")
            
            # Download main file
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(destination, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Progress indicator
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\rProgress: {progress:.1f}%", end="", flush=True)
            
            print()  # New line after progress
            
            # Verify checksum if requested
            if verify_checksum:
                if not self._verify_checksum(filename, destination):
                    self.logger.error(f"Checksum verification failed for {filename}")
                    return False
                    
            self.logger.info(f"Successfully downloaded {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to download {filename}: {e}")
            return False
    
    def _verify_checksum(self, filename: str, local_file: Path) -> bool:
        """Verify MD5 checksum of downloaded file."""
        checksum_url = urljoin(self.NCBI_FTP_BASE, f"{filename}.md5")
        
        try:
            # Download checksum file
            response = requests.get(checksum_url, timeout=10)
            response.raise_for_status()
            
            expected_hash = response.text.strip().split()[0]
            
            # Calculate actual hash
            hash_md5 = hashlib.md5()
            with open(local_file, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            
            actual_hash = hash_md5.hexdigest()
            
            return expected_hash.lower() == actual_hash.lower()
            
        except Exception as e:
            self.logger.warning(f"Could not verify checksum for {filename}: {e}")
            return True  # Don't fail on checksum verification issues
    
    def extract_database(self, tar_file: Path, extract_dir: Path) -> bool:
        """
        Extract downloaded tar.gz database file.
        
        Parameters:
        -----------
        tar_file : Path
            Path to tar.gz file
        extract_dir : Path
            Directory to extract to
            
        Returns:
        --------
        bool: Success status
        """
        try:
            self.logger.info(f"Extracting {tar_file.name}...")
            
            with tarfile.open(tar_file, 'r:gz') as tar:
                tar.extractall(path=extract_dir)
            
            self.logger.info(f"Successfully extracted {tar_file.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to extract {tar_file.name}: {e}")
            return False
    
    def download_database(self, db_name: str, extract: bool = True, 
                         cleanup_tar: bool = True) -> bool:
        """
        Download and optionally extract a complete database.
        
        Parameters:
        -----------
        db_name : str
            Name of database to download
        extract : bool
            Whether to extract tar files
        cleanup_tar : bool
            Whether to delete tar files after extraction
            
        Returns:
        --------
        bool: Success status
        """
        if db_name not in self.AVAILABLE_DATABASES:
            self.logger.error(f"Unknown database: {db_name}")
            return False
        
        self.logger.info(f"Starting download of {db_name} database")
        
        # Get available files
        available_files = self.get_available_files()
        if db_name not in available_files or not available_files[db_name]:
            self.logger.error(f"No files found for database {db_name}")
            return False
        
        files_to_download = available_files[db_name]
        
        # Create database-specific directories
        raw_dir = self.db_dir / "raw" / db_name
        processed_dir = self.db_dir / "processed" / db_name
        raw_dir.mkdir(parents=True, exist_ok=True)
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        # Download all files
        success_count = 0
        for filename in files_to_download:
            destination = raw_dir / filename
            
            # Skip if already downloaded and verified
            if destination.exists():
                self.logger.info(f"File {filename} already exists, skipping")
                success_count += 1
                continue
            
            if self.download_file(filename, destination):
                success_count += 1
                
                # Extract if requested
                if extract and filename.endswith('.tar.gz'):
                    if self.extract_database(destination, processed_dir):
                        # Clean up tar file if requested
                        if cleanup_tar:
                            destination.unlink()
                            self.logger.info(f"Cleaned up {filename}")
        
        # Update status
        self.db_status[db_name] = {
            "downloaded": success_count,
            "total": len(files_to_download),
            "status": "complete" if success_count == len(files_to_download) else "partial",
            "last_updated": time.time()
        }
        self.save_database_status()
        
        success = success_count == len(files_to_download)
        if success:
            self.logger.info(f"Successfully downloaded {db_name} database")
        else:
            self.logger.warning(f"Partial download of {db_name}: {success_count}/{len(files_to_download)} files")
        
        return success
    
    def download_recommended_databases(self) -> Dict[str, bool]:
        """
        Download recommended databases for deep-sea eDNA analysis.
        
        Returns:
        --------
        Dict mapping database names to success status
        """
        # Recommended databases for eDNA analysis
        recommended = [
            "taxdb",  # Critical - always needed
            "16S_ribosomal_RNA",  # High priority - prokaryotes
            "18S_fungal_sequences",  # High priority - fungi  
            "28S_fungal_sequences",  # High priority - fungi
            "ITS_eukaryote_sequences",  # High priority - eukaryotes
            "ITS_RefSeq_Fungi",  # High priority - fungi
        ]
        
        results = {}
        
        self.logger.info("Starting download of recommended databases for eDNA analysis")
        
        for db_name in recommended:
            self.logger.info(f"Downloading {db_name}...")
            results[db_name] = self.download_database(db_name)
        
        # Optionally download core_nt if user has space
        self.logger.info("Consider downloading core_nt for comprehensive analysis (requires ~200GB)")
        
        return results
    
    def get_database_info(self) -> Dict[str, Dict]:
        """Get information about available databases."""
        info = {}
        
        for db_name, db_details in self.AVAILABLE_DATABASES.items():
            status = self.db_status.get(db_name, {"status": "not_downloaded"})
            
            info[db_name] = {
                **db_details,
                **status,
                "local_path": self.db_dir / "processed" / db_name
            }
            
        return info
    
    def create_blast_databases(self) -> Dict[str, bool]:
        """
        Create BLAST+ databases from downloaded files.
        
        Returns:
        --------
        Dict mapping database names to success status
        """
        results = {}
        
        for db_name in self.db_status:
            if self.db_status[db_name]["status"] == "complete":
                processed_dir = self.db_dir / "processed" / db_name
                
                # Look for BLAST database files
                blast_files = list(processed_dir.glob("*.n*"))
                
                if blast_files:
                    self.logger.info(f"BLAST database files found for {db_name}")
                    results[db_name] = True
                else:
                    self.logger.warning(f"No BLAST database files found for {db_name}")
                    results[db_name] = False
        
        return results
    
    def get_blast_db_path(self, db_name: str) -> Optional[str]:
        """
        Get the path to a BLAST database.
        
        Parameters:
        -----------
        db_name : str
            Database name
            
        Returns:
        --------
        str or None: Path to database or None if not available
        """
        if db_name not in self.db_status:
            return None
            
        if self.db_status[db_name]["status"] != "complete":
            return None
        
        processed_dir = self.db_dir / "processed" / db_name
        
        # Look for main database file (usually .pal for protein, .nal for nucleotide)
        db_files = list(processed_dir.glob("*.nal")) + list(processed_dir.glob("*.pal"))

        if db_files:
            # Return path without extension for BLAST
            return str(db_files[0]).rsplit('.', 1)[0]

        # Fallback: detect BLAST databases by core index files (e.g., .nhr/.nin/.nsq)
        nucleotide_suffixes = [".nhr", ".nin", ".nsq"]
        for suffix in nucleotide_suffixes:
            files = list(processed_dir.glob(f"*{suffix}"))
            if files:
                return str(files[0])[:-len(suffix)]

        return None

    def cleanup_downloads(self, keep_processed: bool = True):
        """
        Clean up downloaded files to save space.
        
        Parameters:
        -----------
        keep_processed : bool
            Whether to keep processed/extracted databases
        """
        raw_dir = self.db_dir / "raw"
        
        if raw_dir.exists():
            import shutil
            self.logger.info("Cleaning up raw download files...")
            shutil.rmtree(raw_dir)
            
        if not keep_processed:
            processed_dir = self.db_dir / "processed"
            if processed_dir.exists():
                self.logger.info("Cleaning up processed database files...")
                shutil.rmtree(processed_dir)
                self.db_status = {}
                self.save_database_status()