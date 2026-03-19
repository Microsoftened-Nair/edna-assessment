"""
Database Manager Module for eDNA Analysis Pipeline

This module handles downloading, managing, and updating reference databases
from NCBI and other sources for taxonomic classification.

Key improvements over initial version:
- Database catalogue corrected against live FTP inventory (March 2026)
- Added SSU_eukaryote_rRNA, mito, env_nt — the three most relevant for deep-sea eDNA
- Removed non-existent ref_euk_rep_genomes and refseq_rna entries
- Resume-capable downloads using HTTP Range headers (critical for 2.5 GB+ chunks)
- Dynamic multi-part file discovery by scraping the live FTP index
- Correct eDNA-priority ordering in download_recommended_databases()
- Per-chunk MD5 verification before extraction
"""

import hashlib
import json
import logging
import os
import re
import shutil
import tarfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests


class DatabaseManager:
    """
    Manages reference databases for eDNA taxonomic classification.

    Supports downloading pre-built NCBI BLAST databases from:
        https://ftp.ncbi.nlm.nih.gov/blast/db/

    Priority order for deep-sea eukaryotic eDNA (18S / COI markers):
        1. SSU_eukaryote_rRNA  — 18S primary marker (all eukaryotes, 57 MB)
        2. mito                — COI primary marker (mitochondria, 193 MB)
        3. env_nt              — Environmental sequences (metagenomics, 362 MB)
        4. ITS_eukaryote_sequences — ITS for protists / fungi (74 MB)
        5. LSU_eukaryote_rRNA  — 28S secondary marker (57 MB)
        6. nt_euk              — Full eukaryote nucleotide DB (~570 GB, optional)
        7. core_nt             — Core nucleotide DB (~224 GB, optional)
        8. nt                  — Complete nucleotide DB (~760 GB, comprehensive)
    """

    # NCBI FTP base URL for pre-built BLAST databases
    NCBI_FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/blast/db/"

    # -----------------------------------------------------------------------
    # Database catalogue (verified against FTP index 2026-03-14)
    # -----------------------------------------------------------------------
    AVAILABLE_DATABASES = {
        # === PRIMARY MARKERS FOR DEEP-SEA EUKARYOTIC eDNA ==================
        "SSU_eukaryote_rRNA": {
            "description": (
                "18S Small Subunit rRNA sequences for ALL eukaryotes — "
                "the primary marker gene for deep-sea eukaryotic eDNA metabarcoding"
            ),
            "files": "SSU_eukaryote_rRNA.tar.gz",
            "priority": "critical",
            "use_case": "18S_eDNA_primary_marker",
            "approx_size_mb": 57,
            "multi_part": False,
        },
        "mito": {
            "description": (
                "Mitochondrial sequences database — covers COI (cytochrome oxidase I), "
                "the second primary marker gene for deep-sea eDNA metabarcoding"
            ),
            "files": "mito.tar.gz",
            "priority": "critical",
            "use_case": "COI_eDNA_primary_marker",
            "approx_size_mb": 193,
            "multi_part": False,
        },
        "env_nt": {
            "description": (
                "Environmental nucleotide sequences — specifically targeted at "
                "metagenomics and eDNA samples. Most relevant for novel deep-sea taxa."
            ),
            "files": "env_nt.tar.gz",
            "priority": "high",
            "use_case": "environmental_dna_analysis",
            "approx_size_mb": 362,
            "multi_part": False,
        },

        # === SECONDARY EUKARYOTE MARKERS ====================================
        "ITS_eukaryote_sequences": {
            "description": "ITS (Internal Transcribed Spacer) sequences for eukaryotes",
            "files": "ITS_eukaryote_sequences.tar.gz",
            "priority": "high",
            "use_case": "ITS_eukaryote_marker",
            "approx_size_mb": 74,
            "multi_part": False,
        },
        "LSU_eukaryote_rRNA": {
            "description": (
                "28S Large Subunit rRNA sequences for eukaryotes — "
                "secondary marker for multi-marker approaches"
            ),
            "files": "LSU_eukaryote_rRNA.tar.gz",
            "priority": "high",
            "use_case": "28S_eDNA_secondary_marker",
            "approx_size_mb": 57,
            "multi_part": False,
        },
        "LSU_prokaryote_rRNA": {
            "description": (
                "23S/28S rRNA sequences for prokaryotes — "
                "useful for identifying and filtering prokaryote contamination"
            ),
            "files": "LSU_prokaryote_rRNA.tar.gz",
            "priority": "medium",
            "use_case": "prokaryote_contamination_filter",
            "approx_size_mb": 57,
            "multi_part": False,
        },

        # === FUNGAL / ITS DATABASES =========================================
        "ITS_RefSeq_Fungi": {
            "description": "RefSeq fungal ITS sequences (curated)",
            "files": "ITS_RefSeq_Fungi.tar.gz",
            "priority": "medium",
            "use_case": "fungal_ITS_identification",
            "approx_size_mb": 64,
            "multi_part": False,
        },
        "18S_fungal_sequences": {
            "description": "18S rRNA sequences specifically for fungi",
            "files": "18S_fungal_sequences.tar.gz",
            "priority": "medium",
            "use_case": "fungal_18S_identification",
            "approx_size_mb": 61,
            "multi_part": False,
        },
        "28S_fungal_sequences": {
            "description": "28S rRNA sequences specifically for fungi",
            "files": "28S_fungal_sequences.tar.gz",
            "priority": "medium",
            "use_case": "fungal_28S_identification",
            "approx_size_mb": 63,
            "multi_part": False,
        },

        # === PROKARYOTE MARKER (lower priority for eukaryote pipeline) =======
        "16S_ribosomal_RNA": {
            "description": (
                "16S ribosomal RNA sequences for prokaryotes. "
                "Low priority for a eukaryote-focused eDNA pipeline — "
                "useful only if prokaryote co-detection is required."
            ),
            "files": "16S_ribosomal_RNA.tar.gz",
            "priority": "low",
            "use_case": "prokaryote_identification",
            "approx_size_mb": 67,
            "multi_part": False,
        },

        # === LARGE COMPREHENSIVE DATABASES (optional / storage-permitting) ===
        "nt_euk": {
            "description": (
                "Eukaryotic nucleotide sequences — full eukaryote subset of nt. "
                "Multi-part download (~570 GB total, 200+ chunks of ~2.5 GB each). "
                "Provides the most comprehensive eukaryote coverage."
            ),
            "files": "nt_euk.*.tar.gz",
            "priority": "optional",
            "use_case": "comprehensive_eukaryote_analysis",
            "approx_size_mb": 583_000,
            "multi_part": True,
        },
        "core_nt": {
            "description": (
                "Core NCBI nucleotide database — curated subset of nt. "
                "Multi-part (~224 GB, 87 chunks). Good balance of coverage vs size."
            ),
            "files": "core_nt.*.tar.gz",
            "priority": "optional",
            "use_case": "balanced_nucleotide_analysis",
            "approx_size_mb": 226_000,
            "multi_part": True,
        },
        "nt": {
            "description": (
                "Complete NCBI nucleotide database. "
                "Multi-part (~760 GB, 301 chunks). Use only with ample storage."
            ),
            "files": "nt.*.tar.gz",
            "priority": "low",
            "use_case": "comprehensive_nucleotide_analysis",
            "approx_size_mb": 774_000,
            "multi_part": True,
        },
    }

    # Chunk size for streaming downloads (8 MB)
    _CHUNK_SIZE = 8 * 1024 * 1024

    def __init__(self, db_dir: str = "databases", max_concurrent_downloads: int = 3):
        """
        Initialize DatabaseManager.

        Parameters
        ----------
        db_dir : str
            Directory to store databases.
        max_concurrent_downloads : int
            Maximum number of concurrent downloads (reserved for future async use).
        """
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent_downloads

        self.logger = logging.getLogger(__name__)

        # Subdirectory layout
        (self.db_dir / "raw").mkdir(exist_ok=True)
        (self.db_dir / "processed").mkdir(exist_ok=True)
        (self.db_dir / "logs").mkdir(exist_ok=True)

        # Persistent status tracking
        self.db_status_file = self.db_dir / "database_status.json"
        self.load_database_status()

    # -------------------------------------------------------------------------
    # Status persistence
    # -------------------------------------------------------------------------

    def load_database_status(self):
        """Load database download and processing status from disk."""
        if self.db_status_file.exists():
            try:
                with open(self.db_status_file, "r") as fh:
                    self.db_status = json.load(fh)
            except Exception as exc:
                self.logger.warning("Could not load database status: %s", exc)
                self.db_status = {}
        else:
            self.db_status = {}

    def save_database_status(self):
        """Persist database status to disk."""
        try:
            with open(self.db_status_file, "w") as fh:
                json.dump(self.db_status, fh, indent=2)
        except Exception as exc:
            self.logger.error("Could not save database status: %s", exc)

    # -------------------------------------------------------------------------
    # FTP discovery
    # -------------------------------------------------------------------------

    def get_available_files(self) -> Dict[str, List[str]]:
        """
        Discover available file names for each database by scraping the live FTP index.

        For multi-part databases (e.g. nt_euk.000.tar.gz … nt_euk.220.tar.gz) the
        method discovers ALL parts dynamically rather than relying on a hard-coded count.

        Returns
        -------
        Dict[str, List[str]]
            Mapping of database name → sorted list of filenames available on FTP.
        """
        available_files: Dict[str, List[str]] = {}

        try:
            self.logger.info("Fetching FTP directory listing from NCBI …")
            response = requests.get(self.NCBI_FTP_BASE, timeout=30)
            response.raise_for_status()

            # Extract all .tar.gz href values from the index page
            all_files: List[str] = re.findall(
                r'href="([^"]+\.tar\.gz)"', response.text
            )
            self.logger.info("Found %d tar.gz files on FTP.", len(all_files))

        except Exception as exc:
            self.logger.error("Failed to fetch FTP listing: %s", exc)
            return {}

        for db_name, db_info in self.AVAILABLE_DATABASES.items():
            pattern = db_info["files"]

            if "*" in pattern:
                # Wildcard: match on prefix and suffix
                prefix, suffix = pattern.split("*", 1)
                matching = sorted(
                    f for f in all_files
                    if f.startswith(prefix) and f.endswith(suffix)
                )
            else:
                # Exact match
                matching = [f for f in all_files if f == pattern]

            available_files[db_name] = matching

            if not matching:
                self.logger.warning(
                    "Database '%s' matched 0 files on FTP (pattern: %s). "
                    "It may have been renamed or removed.",
                    db_name, pattern,
                )
            else:
                self.logger.debug(
                    "Database '%s': %d file(s) found.", db_name, len(matching)
                )

        return available_files

    # -------------------------------------------------------------------------
    # File download (with resume support)
    # -------------------------------------------------------------------------

    def download_file(
        self,
        filename: str,
        destination: Path,
        verify_checksum: bool = True,
    ) -> bool:
        """
        Download a single file from NCBI FTP with automatic resume support.

        If the destination file already exists and is partially downloaded, the
        download resumes from where it left off using an HTTP ``Range`` header.

        Parameters
        ----------
        filename : str
            Basename of the file on the FTP server (e.g. ``SSU_eukaryote_rRNA.tar.gz``).
        destination : Path
            Local path to write the file to.
        verify_checksum : bool
            Whether to verify the MD5 checksum after download.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on failure.
        """
        url = urljoin(self.NCBI_FTP_BASE, filename)

        # Determine resume offset
        resume_offset = destination.stat().st_size if destination.exists() else 0

        headers = {}
        if resume_offset > 0:
            headers["Range"] = f"bytes={resume_offset}-"
            self.logger.info(
                "Resuming download of %s from byte %d …", filename, resume_offset
            )
        else:
            self.logger.info("Downloading %s …", filename)

        try:
            response = requests.get(
                url, stream=True, timeout=60, headers=headers
            )

            # 416 = Range Not Satisfiable → file is already complete
            if response.status_code == 416:
                self.logger.info("%s already fully downloaded.", filename)
                return self._verify_checksum(filename, destination) if verify_checksum else True

            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded = resume_offset

            open_mode = "ab" if resume_offset > 0 else "wb"
            with open(destination, open_mode) as fh:
                for chunk in response.iter_content(chunk_size=self._CHUNK_SIZE):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            overall = downloaded / (total_size + resume_offset) * 100
                            print(
                                f"\r  {filename}: {overall:.1f}% "
                                f"({downloaded / 1024 / 1024:.0f} MB)",
                                end="",
                                flush=True,
                            )

            print()  # newline after progress

            if verify_checksum:
                if not self._verify_checksum(filename, destination):
                    self.logger.error("Checksum verification FAILED for %s", filename)
                    return False

            self.logger.info("Successfully downloaded %s.", filename)
            return True

        except Exception as exc:
            self.logger.error("Failed to download %s: %s", filename, exc)
            return False

    # -------------------------------------------------------------------------
    # Checksum verification
    # -------------------------------------------------------------------------

    def _verify_checksum(self, filename: str, local_file: Path) -> bool:
        """
        Verify MD5 checksum of a downloaded file against the NCBI-provided .md5 file.

        On network or parse errors the method logs a warning and returns ``True``
        (non-fatal) to avoid failing a download that is likely valid.

        Parameters
        ----------
        filename : str
            Filename on FTP (used to construct the .md5 URL).
        local_file : Path
            Local file to verify.

        Returns
        -------
        bool
            ``True`` if checksums match (or if verification could not be performed),
            ``False`` if checksums definitively mismatch.
        """
        checksum_url = urljoin(self.NCBI_FTP_BASE, f"{filename}.md5")

        try:
            resp = requests.get(checksum_url, timeout=15)
            resp.raise_for_status()
            # NCBI .md5 format: "<hash>  <filename>"
            expected_hash = resp.text.strip().split()[0].lower()
        except Exception as exc:
            self.logger.warning(
                "Could not fetch checksum for %s (%s) — skipping verification.",
                filename, exc,
            )
            return True

        hash_md5 = hashlib.md5()
        with open(local_file, "rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                hash_md5.update(block)

        actual_hash = hash_md5.hexdigest().lower()

        if expected_hash == actual_hash:
            self.logger.debug("Checksum OK for %s", filename)
            return True

        self.logger.error(
            "Checksum MISMATCH for %s: expected %s, got %s",
            filename, expected_hash, actual_hash,
        )
        return False

    # -------------------------------------------------------------------------
    # Extraction
    # -------------------------------------------------------------------------

    def extract_database(self, tar_file: Path, extract_dir: Path) -> bool:
        """
        Extract a downloaded ``tar.gz`` BLAST database archive.

        Parameters
        ----------
        tar_file : Path
            Path to the ``.tar.gz`` file.
        extract_dir : Path
            Directory to extract into.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on failure.
        """
        try:
            self.logger.info("Extracting %s …", tar_file.name)
            with tarfile.open(tar_file, "r:gz") as tar:
                tar.extractall(path=extract_dir)
            self.logger.info("Extracted %s successfully.", tar_file.name)
            return True
        except Exception as exc:
            self.logger.error("Failed to extract %s: %s", tar_file.name, exc)
            return False

    # -------------------------------------------------------------------------
    # High-level: download a complete database
    # -------------------------------------------------------------------------

    def download_database(
        self,
        db_name: str,
        extract: bool = True,
        cleanup_tar: bool = True,
    ) -> bool:
        """
        Download and optionally extract a complete NCBI BLAST database.

        For multi-part databases (e.g. ``nt_euk``) ALL parts are discovered
        dynamically from the live FTP index and downloaded in order.  Each part
        is extracted immediately after download (to avoid requiring 2× disk space)
        and the tar file is deleted if ``cleanup_tar`` is ``True``.

        Parameters
        ----------
        db_name : str
            Name of the database (must be a key in :attr:`AVAILABLE_DATABASES`).
        extract : bool
            Whether to extract tar archives after download.
        cleanup_tar : bool
            Whether to delete tar archives after successful extraction.

        Returns
        -------
        bool
            ``True`` if ALL files were downloaded (and extracted) successfully.
        """
        if db_name not in self.AVAILABLE_DATABASES:
            self.logger.error(
                "Unknown database: '%s'. Available: %s",
                db_name, list(self.AVAILABLE_DATABASES.keys()),
            )
            return False

        db_meta = self.AVAILABLE_DATABASES[db_name]
        self.logger.info("Starting download of '%s' database …", db_name)

        if db_meta.get("approx_size_mb", 0) > 10_000:
            self.logger.warning(
                "Database '%s' is approximately %d GB. "
                "Ensure sufficient disk space before proceeding.",
                db_name,
                db_meta["approx_size_mb"] // 1024,
            )

        # Discover files on FTP
        available_files = self.get_available_files()
        files_to_download = available_files.get(db_name, [])

        if not files_to_download:
            self.logger.error(
                "No files found on FTP for database '%s'. "
                "Pattern used: '%s'.",
                db_name, db_meta["files"],
            )
            return False

        self.logger.info(
            "Found %d file(s) to download for '%s'.", len(files_to_download), db_name
        )

        # Create local directories
        raw_dir = self.db_dir / "raw" / db_name
        processed_dir = self.db_dir / "processed" / db_name
        raw_dir.mkdir(parents=True, exist_ok=True)
        processed_dir.mkdir(parents=True, exist_ok=True)

        success_count = 0

        for filename in files_to_download:
            destination = raw_dir / filename

            # Skip fully-downloaded & verified files
            if destination.exists():
                if self._verify_checksum(filename, destination):
                    self.logger.info("'%s' already present and verified — skipping.", filename)
                    success_count += 1
                    # Still extract if the processed dir is empty
                    if extract and not any(processed_dir.iterdir()):
                        self.extract_database(destination, processed_dir)
                    continue
                else:
                    self.logger.warning(
                        "'%s' exists but fails checksum — re-downloading.", filename
                    )
                    destination.unlink()

            if self.download_file(filename, destination, verify_checksum=True):
                success_count += 1

                if extract:
                    if self.extract_database(destination, processed_dir):
                        if cleanup_tar:
                            destination.unlink()
                            self.logger.debug("Deleted tar file '%s'.", filename)
                    else:
                        self.logger.error("Extraction failed for '%s'.", filename)
            else:
                self.logger.error("Download failed for '%s'.", filename)

        # Persist status
        total = len(files_to_download)
        status = "complete" if success_count == total else "partial"
        self.db_status[db_name] = {
            "downloaded": success_count,
            "total": total,
            "status": status,
            "last_updated": time.time(),
            "last_updated_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.save_database_status()

        if status == "complete":
            self.logger.info("'%s' database downloaded successfully.", db_name)
        else:
            self.logger.warning(
                "'%s' database partially downloaded: %d/%d files.",
                db_name, success_count, total,
            )

        return status == "complete"

    # -------------------------------------------------------------------------
    # Convenience: download the recommended set for deep-sea eDNA
    # -------------------------------------------------------------------------

    def download_recommended_databases(self) -> Dict[str, bool]:
        """
        Download the recommended database set for deep-sea eukaryotic eDNA analysis.

        Downloads in priority order (smallest / most targeted first):

        1. ``SSU_eukaryote_rRNA``   — 18S primary marker (~57 MB)
        2. ``mito``                 — COI primary marker (~193 MB)
        3. ``env_nt``               — Environmental sequences (~362 MB)
        4. ``ITS_eukaryote_sequences`` — ITS secondary marker (~74 MB)
        5. ``LSU_eukaryote_rRNA``   — 28S secondary marker (~57 MB)

        Larger databases (``nt_euk``, ``core_nt``, ``nt``) are logged as optional
        and must be triggered separately.

        Returns
        -------
        Dict[str, bool]
            Mapping of database name → download success status.
        """
        # Ordered by priority for deep-sea eukaryotic eDNA
        recommended = [
            "SSU_eukaryote_rRNA",       # 18S primary marker   ~57 MB
            "mito",                     # COI primary marker   ~193 MB
            "env_nt",                   # Environmental eDNA   ~362 MB
            "ITS_eukaryote_sequences",  # ITS secondary         ~74 MB
            "LSU_eukaryote_rRNA",       # 28S secondary         ~57 MB
        ]

        self.logger.info(
            "Starting recommended database downloads for deep-sea eukaryotic eDNA analysis."
        )
        self.logger.info(
            "Total estimated download: ~743 MB.  "
            "For comprehensive analysis, also consider 'nt_euk' (~570 GB) or 'core_nt' (~224 GB)."
        )

        results: Dict[str, bool] = {}
        for db_name in recommended:
            self.logger.info("--- Downloading '%s' ---", db_name)
            results[db_name] = self.download_database(db_name)

        successful = sum(1 for ok in results.values() if ok)
        self.logger.info(
            "Recommended download complete: %d/%d databases successful.",
            successful, len(recommended),
        )

        # Advise on optional large databases
        self.logger.info(
            "Optional large databases (not downloaded automatically):\n"
            "  nt_euk  — full eukaryote nucleotide DB (~570 GB)  → run: manager.download_database('nt_euk')\n"
            "  core_nt — core nucleotide DB          (~224 GB)  → run: manager.download_database('core_nt')\n"
            "  nt      — complete nucleotide DB       (~760 GB)  → run: manager.download_database('nt')"
        )

        return results

    # -------------------------------------------------------------------------
    # Database info / path resolution
    # -------------------------------------------------------------------------

    def get_database_info(self) -> Dict[str, Dict]:
        """
        Return a combined view of database metadata and download status.

        Returns
        -------
        Dict[str, Dict]
            Keys are database names; values contain catalogue metadata merged
            with the current download status and local path.
        """
        info: Dict[str, Dict] = {}
        for db_name, db_details in self.AVAILABLE_DATABASES.items():
            status = self.db_status.get(db_name, {"status": "not_downloaded"})
            info[db_name] = {
                **db_details,
                **status,
                "local_path": str(self.db_dir / "processed" / db_name),
            }
        return info

    def get_blast_db_path(self, db_name: str) -> Optional[str]:
        """
        Return the path prefix for a BLAST database, suitable for ``-db`` argument.

        Searches the processed directory for standard BLAST index file extensions
        (``.nal``, ``.pal``, ``.nhr``, ``.nin``, ``.nsq``, ``.nsi``).

        Parameters
        ----------
        db_name : str
            Database name, e.g. ``"SSU_eukaryote_rRNA"``.

        Returns
        -------
        str or None
            Path prefix without extension, or ``None`` if the database is not
            available or has no recognised index files.
        """
        status_entry = self.db_status.get(db_name, {})
        if status_entry.get("status") not in ("complete", "partial"):
            self.logger.debug(
                "Database '%s' is not downloaded (status: %s).",
                db_name, status_entry.get("status", "not_downloaded"),
            )
            return None

        processed_dir = self.db_dir / "processed" / db_name
        if not processed_dir.exists():
            return None

        # Prefer alias files (.nal nucleotide / .pal protein)
        for suffix in (".nal", ".pal"):
            hits = list(processed_dir.glob(f"*{suffix}"))
            if hits:
                return str(hits[0]).removesuffix(suffix)

        # Fall back to core nucleotide index files
        for suffix in (".nhr", ".nin", ".nsq", ".nsi"):
            hits = list(processed_dir.glob(f"*{suffix}"))
            if hits:
                path = str(hits[0])
                return path[: -len(suffix)]

        self.logger.warning(
            "Database '%s' directory exists but contains no recognisable BLAST index files.",
            db_name,
        )
        return None

    # -------------------------------------------------------------------------
    # Maintenance helpers
    # -------------------------------------------------------------------------

    def create_blast_databases(self) -> Dict[str, bool]:
        """
        Check which downloaded databases have valid BLAST index files.

        Pre-built NCBI databases are already indexed; this method verifies
        that the expected index files are present after extraction.

        Returns
        -------
        Dict[str, bool]
            Mapping of database name → ``True`` if BLAST files detected.
        """
        results: Dict[str, bool] = {}

        for db_name, entry in self.db_status.items():
            if entry.get("status") == "complete":
                path = self.get_blast_db_path(db_name)
                results[db_name] = path is not None
                if path:
                    self.logger.info("BLAST database ready: '%s' → %s", db_name, path)
                else:
                    self.logger.warning(
                        "BLAST index files missing for '%s'. Re-extract the archives.",
                        db_name,
                    )

        return results

    def cleanup_downloads(self, keep_processed: bool = True):
        """
        Remove raw download (tar) files to reclaim disk space.

        Parameters
        ----------
        keep_processed : bool
            If ``True`` (default), keep the extracted BLAST database files.
            If ``False``, also removes processed databases and resets status.
        """
        raw_dir = self.db_dir / "raw"

        if raw_dir.exists():
            self.logger.info("Removing raw download directory: %s", raw_dir)
            shutil.rmtree(raw_dir)
        else:
            self.logger.info("No raw download directory found; nothing to clean.")

        if not keep_processed:
            processed_dir = self.db_dir / "processed"
            if processed_dir.exists():
                self.logger.info(
                    "Removing processed database directory: %s", processed_dir
                )
                shutil.rmtree(processed_dir)
            self.db_status = {}
            self.save_database_status()
            self.logger.info("Database status reset.")

    def list_downloaded_databases(self) -> List[str]:
        """
        Return the names of databases that have been fully downloaded.

        Returns
        -------
        List[str]
            Sorted list of database names with status ``"complete"``.
        """
        return sorted(
            name
            for name, entry in self.db_status.items()
            if entry.get("status") == "complete"
        )

    def get_download_summary(self) -> str:
        """
        Return a human-readable summary of database download status.

        Returns
        -------
        str
            Formatted multiline summary string.
        """
        lines = ["Deep-Sea eDNA Database Status", "=" * 40]

        for db_name, db_info in self.AVAILABLE_DATABASES.items():
            entry = self.db_status.get(db_name, {})
            status = entry.get("status", "not_downloaded")
            downloaded = entry.get("downloaded", 0)
            total = entry.get("total", "?")
            size_mb = db_info.get("approx_size_mb", "?")
            priority = db_info.get("priority", "?")

            if status == "complete":
                indicator = "✓"
            elif status == "partial":
                indicator = "~"
            else:
                indicator = "✗"

            size_str = (
                f"{size_mb / 1024:.0f} GB"
                if isinstance(size_mb, int) and size_mb > 1024
                else f"{size_mb} MB"
            )

            lines.append(
                f"{indicator} {db_name:<30} [{priority:<8}] {size_str:>9}  "
                f"status={status}"
                + (f" ({downloaded}/{total} parts)" if status == "partial" else "")
            )

        return "\n".join(lines)