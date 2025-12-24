"""Main pipeline orchestrator for the AI-driven deep-sea eDNA analysis pipeline."""

import os
import json
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import logging
import pickle
from datetime import datetime

from edna_pipeline.config import Config
from edna_pipeline.preprocessing import SequencePreprocessor
from edna_pipeline.feature_engineering import FeatureProcessor
from edna_pipeline.database_manager import DatabaseManager
from edna_pipeline.taxonomic_assignment import TaxonomicAssigner, TaxonomicAssignment
from edna_pipeline.utils.io_utils import read_fastq, read_fasta
from edna_pipeline.utils.data_utils import create_abundance_matrix, normalize_counts, calculate_alpha_diversity

logger = logging.getLogger(__name__)


class DeepSeaEDNAPipeline:
    """
    Main pipeline class for AI-driven deep-sea eDNA analysis.
    
    This class orchestrates the complete pipeline from raw sequencing data
    to final taxonomic classification, abundance estimation, and biodiversity assessment.
    """
    
    def __init__(self, config_path: Optional[str] = None, db_dir: str = "databases"):
        """
        Initialize the eDNA analysis pipeline.
        
        Args:
            config_path: Path to configuration file (YAML format)
            db_dir: Directory containing reference databases
        """
        # Load configuration
        self.config = Config(config_path)
        
        # Initialize pipeline components
        self.preprocessor = SequencePreprocessor(self.config.to_dict())
        self.feature_processor = FeatureProcessor(self.config.to_dict())
        
        # Initialize database manager and taxonomic assigner
        self.db_manager = DatabaseManager(db_dir)
        self.taxonomic_assigner = TaxonomicAssigner(self.db_manager)
        
        # Pipeline state
        self.is_trained = False
        self.training_data = None
        self.processing_history = []
        
        # Setup logging
        self._setup_logging()
        
        logger.info("Initialized DeepSeaEDNAPipeline")
        logger.info(f"Configuration loaded from: {config_path or 'default'}")
        logger.info(f"Database directory: {db_dir}")
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_level = self.config.get("output.log_level", "INFO")
        
        # Configure logging format
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    def process_sample(self, input_files: Union[str, List[str], tuple], 
                      sample_id: Optional[str] = None,
                      output_dir: str = "results") -> Dict[str, Any]:
        """
        Process a single sample through the complete pipeline.
        
        Args:
            input_files: Path to FASTQ file(s). Single string for single-end,
                        tuple/list of 2 strings for paired-end
            sample_id: Sample identifier (auto-generated if None)
            output_dir: Output directory for results
            
        Returns:
            Dictionary with processing results
        """
        start_time = datetime.now()
        
        # Determine input type and sample ID
        if isinstance(input_files, (list, tuple)) and len(input_files) == 2:
            input_type = "paired"
            forward_file, reverse_file = input_files
            if sample_id is None:
                sample_id = Path(forward_file).stem.replace("_R1", "").replace("_1", "")
        else:
            input_type = "single"
            input_file = input_files
            if sample_id is None:
                sample_id = Path(input_file).stem
        
        logger.info(f"Processing sample: {sample_id} ({input_type}-end)")
        
        # Create sample-specific output directory
        sample_output_dir = os.path.join(output_dir, sample_id)
        os.makedirs(sample_output_dir, exist_ok=True)
        
        results = {
            "sample_id": sample_id,
            "input_type": input_type,
            "input_files": input_files,
            "output_dir": sample_output_dir,
            "start_time": start_time.isoformat(),
            "pipeline_steps": []
        }
        
        try:
            # Step 1: Preprocessing
            logger.info("Step 1: Sequence preprocessing")
            if input_type == "paired":
                preprocessing_results = self.preprocessor.process_paired_end_reads(
                    forward_file, reverse_file, sample_output_dir, sample_id
                )
            else:
                preprocessing_results = self.preprocessor.process_single_end_reads(
                    input_file, sample_output_dir, sample_id
                )
            
            results["pipeline_steps"].append({
                "step": "preprocessing",
                "status": "completed" if preprocessing_results.get("success", False) else "failed",
                "results": preprocessing_results
            })
            
            if not preprocessing_results.get("success", False):
                raise RuntimeError("Preprocessing failed")
            
            # Load ASVs for downstream analysis
            asv_file = preprocessing_results["final_asv_file"]
            asvs = read_fasta(asv_file)
            abundance_table = preprocessing_results["abundance_table"]
            
            logger.info(f"Loaded {len(asvs)} ASVs for analysis")
            
            # Step 2: Feature extraction
            logger.info("Step 2: Feature extraction")
            feature_results = self._extract_features(asvs, sample_output_dir)
            results["pipeline_steps"].append({
                "step": "feature_extraction",
                "status": "completed",
                "results": feature_results
            })
            
            # Step 3: Taxonomic classification (placeholder - would need trained models)
            logger.info("Step 3: Taxonomic classification")
            classification_results = self._classify_sequences(asvs, abundance_table, sample_output_dir)
            results["pipeline_steps"].append({
                "step": "taxonomic_classification",
                "status": "completed",
                "results": classification_results
            })
            
            # Step 4: Abundance quantification and diversity analysis
            logger.info("Step 4: Abundance quantification and diversity analysis")
            abundance_results = self._quantify_abundance(
                abundance_table, classification_results.get("taxonomy", {}), sample_output_dir
            )
            results["pipeline_steps"].append({
                "step": "abundance_quantification",
                "status": "completed",
                "results": abundance_results
            })
            
            # Step 5: Generate summary report
            logger.info("Step 5: Generating summary report")
            report_results = self._generate_sample_report(results, sample_output_dir)
            results["pipeline_steps"].append({
                "step": "report_generation",
                "status": "completed",
                "results": report_results
            })
            
            # Mark as successful
            results["success"] = True
            end_time = datetime.now()
            results["end_time"] = end_time.isoformat()
            results["processing_time"] = (end_time - start_time).total_seconds()
            
            logger.info(f"Sample processing completed successfully: {sample_id}")
            logger.info(f"Processing time: {results['processing_time']:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Pipeline failed for sample {sample_id}: {str(e)}")
            results["success"] = False
            results["error"] = str(e)
            results["end_time"] = datetime.now().isoformat()
            raise
        
        # Add to processing history
        self.processing_history.append(results)
        
        # Save results
        results_file = os.path.join(sample_output_dir, "pipeline_results.json")
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        return results
    
    def _extract_features(self, asvs: List, output_dir: str) -> Dict[str, Any]:
        """Extract features from ASV sequences."""
        try:
            # Extract features using feature processor
            features = self.feature_processor.extract_all_features(asvs)
            
            # Save feature statistics
            stats_file = os.path.join(output_dir, "feature_statistics.txt")
            self.feature_processor.save_feature_stats(asvs, stats_file)
            
            # Get recommended feature types
            recommended_features = self.feature_processor.get_recommended_feature_types(asvs)
            
            results = {
                "total_asvs": len(asvs),
                "feature_types": list(features.keys()),
                "feature_shapes": {k: list(v.shape) for k, v in features.items()},
                "recommended_features": recommended_features,
                "statistics_file": stats_file
            }
            
            # Save features
            features_file = os.path.join(output_dir, "features.pkl")
            with open(features_file, 'wb') as f:
                pickle.dump(features, f)
            results["features_file"] = features_file
            
            return results
            
        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            return {"error": str(e)}
    
    def _classify_sequences(self, asvs: List, abundance_table: Dict[str, int], 
                           output_dir: str) -> Dict[str, Any]:
        """
        Classify ASV sequences taxonomically using reference databases.
        
        This uses BLAST searches against NCBI databases and machine learning
        methods for robust taxonomic assignment.
        """
        logger.info(f"Starting taxonomic classification of {len(asvs)} ASVs...")
        
        # Get classification methods from config
        methods = self.config.get("taxonomy.methods", ["blast", "kmer"])
        
        # Run taxonomic assignment
        assignments = self.taxonomic_assigner.assign_taxonomy(asvs, methods)
        
        # Convert to legacy format for compatibility
        taxonomy = {}
        confidence_scores = {}
        
        for asv_id, assignment in assignments.items():
            taxonomy[asv_id] = {
                "domain": assignment.kingdom,  # Map kingdom to domain for compatibility
                "phylum": assignment.phylum,
                "class": assignment.class_name,
                "order": assignment.order,
                "family": assignment.family,
                "genus": assignment.genus,
                "species": assignment.species
            }
            confidence_scores[asv_id] = assignment.confidence / 100.0  # Convert to 0-1 scale
        
        # Save detailed taxonomy results
        taxonomy_file = os.path.join(output_dir, "taxonomy.json")
        with open(taxonomy_file, 'w') as f:
            json.dump(taxonomy, f, indent=2)
        
        # Save detailed assignments
        detailed_file = os.path.join(output_dir, "taxonomic_assignments.csv")
        self.taxonomic_assigner.save_results(assignments, detailed_file)
        
        # Generate summary report
        summary = self.taxonomic_assigner.generate_summary_report(assignments)
        summary_file = os.path.join(output_dir, "taxonomy_summary.json")
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        # Create taxonomy summary for legacy compatibility
        phylum_counts = {}
        for asv_tax in taxonomy.values():
            phylum = asv_tax.get("phylum", "Unknown")
            phylum_counts[phylum] = phylum_counts.get(phylum, 0) + 1
        
        results = {
            "total_classified": len([a for a in assignments.values() if a.kingdom != "Unknown"]),
            "taxonomy": taxonomy,
            "confidence_scores": confidence_scores,
            "taxonomy_file": taxonomy_file,
            "detailed_file": detailed_file,
            "summary_file": summary_file,
            "phylum_distribution": phylum_counts,
            "classification_method": ", ".join(methods),
            "mean_confidence": summary.get("mean_confidence", 0.0),
            "classification_summary": summary
        }
        
        logger.info(f"Classification completed: {results['total_classified']}/{len(asvs)} ASVs classified")
        logger.info(f"Mean confidence: {results['mean_confidence']:.2f}%")
        
        return results
    
    def _quantify_abundance(self, abundance_table: Dict[str, int], 
                           taxonomy: Dict[str, Dict], output_dir: str) -> Dict[str, Any]:
        """Quantify abundance and calculate diversity metrics."""
        try:
            import pandas as pd
            
            # Create abundance matrix (single sample)
            sample_name = "sample"
            abundance_matrix = pd.DataFrame([abundance_table]).T
            abundance_matrix.columns = [sample_name]
            abundance_matrix.index.name = "ASV_ID"
            
            # Calculate diversity metrics
            diversity_metrics = calculate_alpha_diversity(abundance_matrix.T)
            
            # Normalize abundances
            normalized_abundance = normalize_counts(
                abundance_matrix.T, 
                method=self.config.get("abundance.normalization_method", "relative")
            )
            
            # Create taxonomic summary
            taxonomic_abundance = self._create_taxonomic_abundance(
                abundance_table, taxonomy
            )
            
            # Save results
            abundance_file = os.path.join(output_dir, "abundance_matrix.csv")
            abundance_matrix.to_csv(abundance_file)
            
            normalized_file = os.path.join(output_dir, "normalized_abundance.csv")
            normalized_abundance.to_csv(normalized_file)
            
            diversity_file = os.path.join(output_dir, "diversity_metrics.csv")
            diversity_metrics.to_csv(diversity_file)
            
            taxonomic_file = os.path.join(output_dir, "taxonomic_abundance.json")
            with open(taxonomic_file, 'w') as f:
                json.dump(taxonomic_abundance, f, indent=2)
            
            results = {
                "total_reads": sum(abundance_table.values()),
                "total_asvs": len(abundance_table),
                "diversity_metrics": diversity_metrics.to_dict(),
                "taxonomic_summary": taxonomic_abundance,
                "abundance_file": abundance_file,
                "normalized_file": normalized_file,
                "diversity_file": diversity_file,
                "taxonomic_file": taxonomic_file
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Abundance quantification failed: {e}")
            return {"error": str(e)}
    
    def _create_taxonomic_abundance(self, abundance_table: Dict[str, int], 
                                   taxonomy: Dict[str, Dict]) -> Dict[str, Dict]:
        """Create abundance summary at different taxonomic levels."""
        taxonomic_abundance = {}
        
        # Initialize counters for each taxonomic level
        levels = ["domain", "phylum", "class", "order", "family", "genus", "species"]
        for level in levels:
            taxonomic_abundance[level] = {}
        
        # Aggregate abundances by taxonomic level
        for asv_id, abundance in abundance_table.items():
            if asv_id in taxonomy:
                tax_info = taxonomy[asv_id]
                
                for level in levels:
                    taxon_name = tax_info.get(level, "Unknown")
                    if taxon_name not in taxonomic_abundance[level]:
                        taxonomic_abundance[level][taxon_name] = 0
                    taxonomic_abundance[level][taxon_name] += abundance
        
        return taxonomic_abundance
    
    def _generate_sample_report(self, results: Dict[str, Any], output_dir: str) -> Dict[str, Any]:
        """Generate comprehensive sample report."""
        try:
            report_file = os.path.join(output_dir, "sample_report.html")
            
            # Extract key metrics
            preprocessing_step = next(s for s in results["pipeline_steps"] if s["step"] == "preprocessing")
            feature_step = next(s for s in results["pipeline_steps"] if s["step"] == "feature_extraction")
            classification_step = next(s for s in results["pipeline_steps"] if s["step"] == "taxonomic_classification")
            abundance_step = next(s for s in results["pipeline_steps"] if s["step"] == "abundance_quantification")
            
            # Generate HTML report
            html_content = self._create_html_report(
                results["sample_id"],
                preprocessing_step["results"],
                feature_step["results"],
                classification_step["results"],
                abundance_step["results"]
            )
            
            with open(report_file, 'w') as f:
                f.write(html_content)
            
            return {
                "report_file": report_file,
                "report_format": "html"
            }
            
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return {"error": str(e)}
    
    def _create_html_report(self, sample_id: str, preprocessing: Dict, 
                           features: Dict, classification: Dict, abundance: Dict) -> str:
        """Create HTML report content."""
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>eDNA Analysis Report - {sample_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #2c3e50; color: white; padding: 20px; text-align: center; }}
                .section {{ margin: 20px 0; padding: 15px; border-left: 4px solid #3498db; }}
                .metric {{ display: inline-block; margin: 10px 20px; }}
                .metric-value {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
                .metric-label {{ font-size: 14px; color: #7f8c8d; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Deep-Sea eDNA Analysis Report</h1>
                <h2>Sample: {sample_id}</h2>
                <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="section">
                <h2>🧬 Preprocessing Summary</h2>
                <div class="metric">
                    <div class="metric-value">{preprocessing.get('final_asvs', 'N/A')}</div>
                    <div class="metric-label">Total ASVs</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{len(preprocessing.get('processing_steps', []))}</div>
                    <div class="metric-label">Processing Steps</div>
                </div>
            </div>
            
            <div class="section">
                <h2>🔬 Feature Analysis</h2>
                <div class="metric">
                    <div class="metric-value">{len(features.get('feature_types', []))}</div>
                    <div class="metric-label">Feature Types</div>
                </div>
                <p><strong>Recommended Features:</strong> {', '.join(features.get('recommended_features', []))}</p>
            </div>
            
            <div class="section">
                <h2>📊 Taxonomic Classification</h2>
                <div class="metric">
                    <div class="metric-value">{classification.get('total_classified', 'N/A')}</div>
                    <div class="metric-label">Classified ASVs</div>
                </div>
                
                <h3>Phylum Distribution</h3>
                <table>
                    <tr><th>Phylum</th><th>Count</th></tr>
        """
        
        # Add phylum distribution table
        phylum_dist = classification.get('phylum_distribution', {})
        for phylum, count in sorted(phylum_dist.items(), key=lambda x: x[1], reverse=True):
            html_template += f"<tr><td>{phylum}</td><td>{count}</td></tr>"
        
        html_template += f"""
                </table>
            </div>
            
            <div class="section">
                <h2>📈 Abundance & Diversity</h2>
                <div class="metric">
                    <div class="metric-value">{abundance.get('total_reads', 'N/A'):,}</div>
                    <div class="metric-label">Total Reads</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{abundance.get('total_asvs', 'N/A')}</div>
                    <div class="metric-label">Total ASVs</div>
                </div>
                
                <h3>Alpha Diversity Metrics</h3>
                <table>
                    <tr><th>Metric</th><th>Value</th></tr>
        """
        
        # Add diversity metrics
        diversity_metrics = abundance.get('diversity_metrics', {})
        for sample, metrics in diversity_metrics.items():
            for metric, value in metrics.items():
                html_template += f"<tr><td>{metric.capitalize()}</td><td>{value:.3f}</td></tr>"
        
        html_template += """
                </table>
            </div>
            
            <div class="section">
                <h2>📋 File Outputs</h2>
                <ul>
        """
        
        # Add output files
        output_files = [
            preprocessing.get('final_asv_file'),
            features.get('features_file'),
            classification.get('taxonomy_file'),
            abundance.get('abundance_file'),
            abundance.get('diversity_file')
        ]
        
        for file_path in output_files:
            if file_path:
                filename = os.path.basename(file_path)
                html_template += f"<li>{filename}</li>"
        
        html_template += """
                </ul>
            </div>
        </body>
        </html>
        """
        
        return html_template
    
    def process_batch(self, sample_list: List[Dict[str, Any]], 
                     output_dir: str = "batch_results") -> Dict[str, Any]:
        """
        Process multiple samples in batch.
        
        Args:
            sample_list: List of sample dictionaries with 'files' and optional 'sample_id'
            output_dir: Output directory for batch results
            
        Returns:
            Batch processing results
        """
        logger.info(f"Starting batch processing of {len(sample_list)} samples")
        
        batch_start_time = datetime.now()
        batch_results = {
            "total_samples": len(sample_list),
            "successful_samples": 0,
            "failed_samples": 0,
            "sample_results": {},
            "start_time": batch_start_time.isoformat(),
            "output_dir": output_dir
        }
        
        os.makedirs(output_dir, exist_ok=True)
        
        for i, sample_info in enumerate(sample_list, 1):
            sample_files = sample_info["files"]
            sample_id = sample_info.get("sample_id")
            
            logger.info(f"Processing sample {i}/{len(sample_list)}: {sample_id or 'auto-generated'}")
            
            try:
                result = self.process_sample(
                    input_files=sample_files,
                    sample_id=sample_id,
                    output_dir=output_dir
                )
                
                if result.get("success", False):
                    batch_results["successful_samples"] += 1
                else:
                    batch_results["failed_samples"] += 1
                
                batch_results["sample_results"][result["sample_id"]] = result
                
            except Exception as e:
                logger.error(f"Failed to process sample {i}: {str(e)}")
                batch_results["failed_samples"] += 1
                
                if sample_id:
                    batch_results["sample_results"][sample_id] = {
                        "success": False,
                        "error": str(e)
                    }
        
        batch_end_time = datetime.now()
        batch_results["end_time"] = batch_end_time.isoformat()
        batch_results["total_processing_time"] = (batch_end_time - batch_start_time).total_seconds()
        
        # Generate batch summary report
        batch_summary = self._generate_batch_summary(batch_results, output_dir)
        batch_results["summary_report"] = batch_summary
        
        # Save batch results
        batch_results_file = os.path.join(output_dir, "batch_results.json")
        with open(batch_results_file, 'w') as f:
            json.dump(batch_results, f, indent=2, default=str)
        
        logger.info(f"Batch processing completed: {batch_results['successful_samples']}/{len(sample_list)} successful")
        
        return batch_results
    
    def _generate_batch_summary(self, batch_results: Dict[str, Any], 
                               output_dir: str) -> Dict[str, Any]:
        """Generate batch processing summary."""
        summary_file = os.path.join(output_dir, "batch_summary.html")
        
        # Calculate summary statistics
        successful_results = [
            result for result in batch_results["sample_results"].values()
            if result.get("success", False)
        ]
        
        if successful_results:
            # Aggregate statistics across all samples
            total_asvs = sum(
                len(result["pipeline_steps"][0]["results"].get("abundance_table", {}))
                for result in successful_results
            )
            
            avg_processing_time = sum(
                result.get("processing_time", 0) for result in successful_results
            ) / len(successful_results)
        else:
            total_asvs = 0
            avg_processing_time = 0
        
        # Generate HTML summary
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Batch eDNA Analysis Summary</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #2c3e50; color: white; padding: 20px; text-align: center; }}
                .metric {{ display: inline-block; margin: 20px; text-align: center; }}
                .metric-value {{ font-size: 36px; font-weight: bold; color: #2c3e50; }}
                .metric-label {{ font-size: 16px; color: #7f8c8d; }}
                .success {{ color: #27ae60; }}
                .error {{ color: #e74c3c; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Batch eDNA Analysis Summary</h1>
                <p>Processing completed on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div style="text-align: center; margin: 40px 0;">
                <div class="metric">
                    <div class="metric-value">{batch_results['total_samples']}</div>
                    <div class="metric-label">Total Samples</div>
                </div>
                
                <div class="metric">
                    <div class="metric-value success">{batch_results['successful_samples']}</div>
                    <div class="metric-label">Successful</div>
                </div>
                
                <div class="metric">
                    <div class="metric-value error">{batch_results['failed_samples']}</div>
                    <div class="metric-label">Failed</div>
                </div>
                
                <div class="metric">
                    <div class="metric-value">{total_asvs:,}</div>
                    <div class="metric-label">Total ASVs</div>
                </div>
                
                <div class="metric">
                    <div class="metric-value">{avg_processing_time:.1f}s</div>
                    <div class="metric-label">Avg. Processing Time</div>
                </div>
            </div>
            
            <h2>Sample Processing Status</h2>
            <ul>
        """
        
        for sample_id, result in batch_results["sample_results"].items():
            status = "✅ Success" if result.get("success", False) else "❌ Failed"
            html_content += f"<li><strong>{sample_id}:</strong> {status}</li>"
        
        html_content += """
            </ul>
        </body>
        </html>
        """
        
        with open(summary_file, 'w') as f:
            f.write(html_content)
        
        return {
            "summary_file": summary_file,
            "total_asvs": total_asvs,
            "average_processing_time": avg_processing_time,
            "success_rate": batch_results["successful_samples"] / batch_results["total_samples"]
        }
    
    def save_pipeline_state(self, output_path: str):
        """Save pipeline state for future use."""
        state = {
            "config": self.config.to_dict(),
            "is_trained": self.is_trained,
            "processing_history": self.processing_history,
            "pipeline_version": "1.0.0"
        }
        
        with open(output_path, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        
        logger.info(f"Pipeline state saved to {output_path}")
    
    def load_pipeline_state(self, input_path: str):
        """Load previously saved pipeline state."""
        try:
            with open(input_path, 'r') as f:
                state = json.load(f)
            
            self.is_trained = state.get("is_trained", False)
            self.processing_history = state.get("processing_history", [])
            
            logger.info(f"Pipeline state loaded from {input_path}")
            
        except Exception as e:
            logger.error(f"Failed to load pipeline state: {e}")
            raise