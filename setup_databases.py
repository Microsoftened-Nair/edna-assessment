#!/usr/bin/env python3
"""
Database Setup Utility for eDNA Analysis Pipeline

This script helps download and set up reference databases from NCBI
for use with the eDNA analysis pipeline.
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add the pipeline directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "edna_pipeline"))

from database_manager import DatabaseManager

def setup_logging(verbose: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('database_setup.log')
        ]
    )

def main():
    parser = argparse.ArgumentParser(
        description='Download and set up reference databases for eDNA analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download recommended databases for eDNA analysis
  python setup_databases.py --recommended

  # Download specific databases
  python setup_databases.py --databases 16S_ribosomal_RNA taxdb ITS_eukaryote_sequences

  # Download all small databases (< 1GB each)
  python setup_databases.py --small-only

  # Show available databases without downloading
  python setup_databases.py --list

  # Download with custom database directory
  python setup_databases.py --recommended --db-dir /path/to/databases
        """
    )
    
    parser.add_argument(
        '--recommended', 
        action='store_true',
        help='Download recommended databases for eDNA analysis'
    )
    
    parser.add_argument(
        '--databases', 
        nargs='+',
        help='Specific databases to download'
    )
    
    parser.add_argument(
        '--small-only', 
        action='store_true',
        help='Download only small databases (< 1GB)'
    )
    
    parser.add_argument(
        '--list', 
        action='store_true',
        help='List available databases and exit'
    )
    
    parser.add_argument(
        '--db-dir', 
        default='databases',
        help='Directory to store databases (default: databases)'
    )
    
    parser.add_argument(
        '--no-extract', 
        action='store_true',
        help='Download but do not extract tar files'
    )
    
    parser.add_argument(
        '--keep-tar', 
        action='store_true',
        help='Keep tar files after extraction'
    )
    
    parser.add_argument(
        '--verbose', '-v', 
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Initialize database manager
    db_manager = DatabaseManager(args.db_dir)
    
    # List databases if requested
    if args.list:
        print("\nAvailable Databases for eDNA Analysis:")
        print("=" * 60)
        
        info = db_manager.get_database_info()
        
        # Group by priority
        priorities = ['critical', 'high', 'medium', 'low']
        for priority in priorities:
            print(f"\n{priority.upper()} PRIORITY:")
            print("-" * 30)
            
            for db_name, db_info in info.items():
                if db_info['priority'] == priority:
                    status = db_info.get('status', 'not_downloaded')
                    status_indicator = "✓" if status == "complete" else "✗"
                    
                    print(f"  {status_indicator} {db_name:25} - {db_info['description']}")
                    print(f"    {'':27} Use case: {db_info['use_case']}")
        
        print(f"\nDatabase directory: {db_manager.db_dir}")
        return
    
    # Check if user specified what to download
    if not any([args.recommended, args.databases, args.small_only]):
        parser.print_help()
        print("\nERROR: Please specify what to download (--recommended, --databases, or --small-only)")
        return 1
    
    logger.info(f"Database directory: {db_manager.db_dir}")
    
    # Determine which databases to download
    databases_to_download = []
    
    if args.recommended:
        # Download recommended databases for eDNA analysis
        databases_to_download = [
            "taxdb",  # Critical - always needed
            "16S_ribosomal_RNA",  # High priority - prokaryotes
            "18S_fungal_sequences",  # High priority - fungi  
            "28S_fungal_sequences",  # High priority - fungi
            "ITS_eukaryote_sequences",  # High priority - eukaryotes
            "ITS_RefSeq_Fungi",  # High priority - fungi
        ]
        
        logger.info("Downloading recommended databases for eDNA analysis")
        
    elif args.small_only:
        # Download only small databases
        small_dbs = [
            "taxdb", "16S_ribosomal_RNA", "18S_fungal_sequences",
            "28S_fungal_sequences", "ITS_eukaryote_sequences", "ITS_RefSeq_Fungi"
        ]
        databases_to_download = small_dbs
        
        logger.info("Downloading small databases only")
        
    elif args.databases:
        databases_to_download = args.databases
        logger.info(f"Downloading specified databases: {databases_to_download}")
    
    # Validate database names
    available_dbs = set(db_manager.AVAILABLE_DATABASES.keys())
    invalid_dbs = set(databases_to_download) - available_dbs
    
    if invalid_dbs:
        logger.error(f"Invalid database names: {invalid_dbs}")
        logger.error(f"Available databases: {list(available_dbs)}")
        return 1
    
    # Show what will be downloaded
    print(f"\nWill download {len(databases_to_download)} databases:")
    total_estimated_size = 0
    
    # Rough size estimates (in MB)
    size_estimates = {
        "taxdb": 58,
        "16S_ribosomal_RNA": 65,
        "18S_fungal_sequences": 58,
        "28S_fungal_sequences": 60,
        "ITS_eukaryote_sequences": 71,
        "ITS_RefSeq_Fungi": 61,
        "core_nt": 200000,  # ~200GB
        "nt_euk": 150000,   # ~150GB
        "nt": 600000,       # ~600GB
        "ref_euk_rep_genomes": 400000,  # ~400GB
        "refseq_rna": 50000  # ~50GB
    }
    
    for db_name in databases_to_download:
        db_info = db_manager.AVAILABLE_DATABASES[db_name]
        estimated_size = size_estimates.get(db_name, 100)
        total_estimated_size += estimated_size
        
        print(f"  • {db_name:25} - {db_info['description']}")
        
        if estimated_size > 1000:
            print(f"    {'':27} Estimated size: {estimated_size/1000:.1f}GB")
        else:
            print(f"    {'':27} Estimated size: {estimated_size}MB")
    
    if total_estimated_size > 1000:
        print(f"\nTotal estimated download size: {total_estimated_size/1000:.1f}GB")
    else:
        print(f"\nTotal estimated download size: {total_estimated_size}MB")
    
    # Warn about large downloads
    if total_estimated_size > 10000:  # > 10GB
        response = input("\nThis is a large download that may take considerable time. Continue? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            print("Download cancelled.")
            return 0
    
    # Download databases
    success_count = 0
    failed_downloads = []
    
    for db_name in databases_to_download:
        try:
            logger.info(f"\nDownloading {db_name}...")
            success = db_manager.download_database(
                db_name, 
                extract=not args.no_extract,
                cleanup_tar=not args.keep_tar
            )
            
            if success:
                success_count += 1
                logger.info(f"✓ Successfully downloaded {db_name}")
            else:
                failed_downloads.append(db_name)
                logger.error(f"✗ Failed to download {db_name}")
                
        except KeyboardInterrupt:
            logger.info("\nDownload interrupted by user")
            break
        except Exception as e:
            logger.error(f"Error downloading {db_name}: {e}")
            failed_downloads.append(db_name)
    
    # Summary
    print(f"\n{'='*60}")
    print("DOWNLOAD SUMMARY")
    print(f"{'='*60}")
    print(f"Successfully downloaded: {success_count}/{len(databases_to_download)} databases")
    
    if failed_downloads:
        print(f"Failed downloads: {failed_downloads}")
        print("You can retry failed downloads by running the script again.")
    
    # Check BLAST database availability
    if success_count > 0:
        logger.info("\nChecking BLAST database availability...")
        blast_status = db_manager.create_blast_databases()
        
        available_blast_dbs = [db for db, status in blast_status.items() if status]
        if available_blast_dbs:
            print(f"\nBLAST databases ready: {available_blast_dbs}")
        
    print(f"\nDatabase directory: {db_manager.db_dir}")
    
    # Provide usage instructions
    if success_count > 0:
        print("\nNEXT STEPS:")
        print("-" * 20)
        print("1. The databases are now ready for use with the eDNA pipeline")
        print("2. You can run the pipeline using:")
        print("   python example_usage.py")
        print("3. Or integrate with your own scripts using:")
        print("   from edna_pipeline import EDNAPipeline")
        
        if args.recommended and "core_nt" not in databases_to_download:
            print("\nOPTIONAL:")
            print("Consider downloading 'core_nt' for more comprehensive analysis:")
            print("python setup_databases.py --databases core_nt")
            print("(Warning: This is ~200GB and will take significant time/space)")
    
    return 0 if success_count == len(databases_to_download) else 1

if __name__ == "__main__":
    sys.exit(main())