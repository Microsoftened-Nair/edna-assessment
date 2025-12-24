"""Data utility functions for abundance matrices and normalization."""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Union, Optional
from collections import Counter
import logging

logger = logging.getLogger(__name__)


def create_abundance_matrix(abundance_tables: Dict[str, Dict[str, int]], 
                           fill_missing: bool = True) -> pd.DataFrame:
    """
    Create abundance matrix from sample abundance tables.
    
    Args:
        abundance_tables: Dictionary mapping sample_id to abundance dictionary
        fill_missing: Whether to fill missing values with 0
        
    Returns:
        DataFrame with samples as rows and taxa as columns
    """
    # Get all unique taxa across all samples
    all_taxa = set()
    for sample_abundances in abundance_tables.values():
        all_taxa.update(sample_abundances.keys())
    
    all_taxa = sorted(list(all_taxa))
    
    # Create matrix
    matrix_data = []
    sample_names = []
    
    for sample_id, abundances in abundance_tables.items():
        sample_row = []
        for taxon in all_taxa:
            abundance = abundances.get(taxon, 0 if fill_missing else np.nan)
            sample_row.append(abundance)
        
        matrix_data.append(sample_row)
        sample_names.append(sample_id)
    
    # Create DataFrame
    abundance_matrix = pd.DataFrame(
        matrix_data,
        index=sample_names,
        columns=all_taxa
    )
    
    logger.info(f"Created abundance matrix: {abundance_matrix.shape}")
    return abundance_matrix


def normalize_counts(abundance_matrix: pd.DataFrame, 
                    method: str = "relative", 
                    rarefaction_depth: Optional[int] = None) -> pd.DataFrame:
    """
    Normalize abundance counts using various methods.
    
    Args:
        abundance_matrix: DataFrame with samples as rows, taxa as columns
        method: Normalization method ('relative', 'rarefaction', 'tpm', 'css')
        rarefaction_depth: Depth for rarefaction (if None, use minimum sample sum)
        
    Returns:
        Normalized abundance matrix
    """
    if method == "relative":
        # Relative abundance (proportions)
        normalized = abundance_matrix.div(abundance_matrix.sum(axis=1), axis=0)
        
    elif method == "rarefaction":
        # Rarefaction to equal sampling depth
        if rarefaction_depth is None:
            rarefaction_depth = int(abundance_matrix.sum(axis=1).min())
        
        logger.info(f"Rarefying to depth: {rarefaction_depth}")
        normalized = _rarefy_samples(abundance_matrix, rarefaction_depth)
        
    elif method == "tpm":
        # TPM-like normalization
        # Normalize by taxon length (assuming equal length here) and sample size
        normalized = abundance_matrix.div(abundance_matrix.sum(axis=1), axis=0) * 1e6
        
    elif method == "css":
        # Cumulative Sum Scaling
        normalized = _css_normalization(abundance_matrix)
        
    else:
        raise ValueError(f"Unknown normalization method: {method}")
    
    logger.info(f"Applied {method} normalization")
    return normalized


def _rarefy_samples(abundance_matrix: pd.DataFrame, depth: int) -> pd.DataFrame:
    """
    Rarefy samples to equal depth using random sampling without replacement.
    
    Args:
        abundance_matrix: Original abundance matrix
        depth: Rarefaction depth
        
    Returns:
        Rarefied abundance matrix
    """
    rarefied_data = []
    
    for sample_id in abundance_matrix.index:
        sample_counts = abundance_matrix.loc[sample_id]
        total_reads = sample_counts.sum()
        
        if total_reads < depth:
            logger.warning(f"Sample {sample_id} has fewer reads ({total_reads}) than rarefaction depth ({depth})")
            # Option 1: Skip this sample (set all counts to 0)
            rarefied_counts = pd.Series(0, index=sample_counts.index)
        else:
            # Create pool of reads for rarefaction
            read_pool = []
            for taxon, count in sample_counts.items():
                read_pool.extend([taxon] * int(count))
            
            # Randomly sample without replacement
            np.random.seed(42)  # For reproducibility
            sampled_reads = np.random.choice(read_pool, size=depth, replace=False)
            
            # Count rarefied abundances
            rarefied_counts = pd.Series(Counter(sampled_reads), index=sample_counts.index).fillna(0)
        
        rarefied_data.append(rarefied_counts)
    
    rarefied_matrix = pd.DataFrame(rarefied_data, index=abundance_matrix.index)
    return rarefied_matrix


def _css_normalization(abundance_matrix: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Cumulative Sum Scaling normalization.
    
    Args:
        abundance_matrix: Original abundance matrix
        
    Returns:
        CSS normalized matrix
    """
    # Calculate cumulative sum scaling factors
    percentile = 50  # Median
    
    css_factors = []
    for sample_id in abundance_matrix.index:
        sample_counts = abundance_matrix.loc[sample_id]
        # Sort counts and calculate cumulative sum
        sorted_counts = np.sort(sample_counts[sample_counts > 0])
        cumsum = np.cumsum(sorted_counts)
        
        # Find percentile position
        percentile_pos = int(len(sorted_counts) * percentile / 100)
        if percentile_pos > 0:
            css_factor = cumsum[percentile_pos - 1]
        else:
            css_factor = sample_counts.sum()
        
        css_factors.append(css_factor)
    
    # Normalize by CSS factors
    css_factors = pd.Series(css_factors, index=abundance_matrix.index)
    normalized = abundance_matrix.div(css_factors, axis=0)
    
    return normalized


def calculate_alpha_diversity(abundance_matrix: pd.DataFrame, 
                            metrics: List[str] = None) -> pd.DataFrame:
    """
    Calculate alpha diversity metrics for each sample.
    
    Args:
        abundance_matrix: DataFrame with samples as rows, taxa as columns
        metrics: List of metrics to calculate ('shannon', 'simpson', 'chao1', 'ace', 'richness')
        
    Returns:
        DataFrame with samples as rows and diversity metrics as columns
    """
    if metrics is None:
        metrics = ['shannon', 'simpson', 'chao1', 'richness']
    
    diversity_data = []
    
    for sample_id in abundance_matrix.index:
        sample_counts = abundance_matrix.loc[sample_id]
        sample_diversity = {}
        
        # Filter out zero counts
        nonzero_counts = sample_counts[sample_counts > 0]
        
        if len(nonzero_counts) == 0:
            # No taxa present
            for metric in metrics:
                sample_diversity[metric] = 0.0
        else:
            # Calculate metrics
            if 'richness' in metrics:
                sample_diversity['richness'] = len(nonzero_counts)
            
            if 'shannon' in metrics:
                sample_diversity['shannon'] = _shannon_diversity(nonzero_counts)
            
            if 'simpson' in metrics:
                sample_diversity['simpson'] = _simpson_diversity(nonzero_counts)
            
            if 'chao1' in metrics:
                sample_diversity['chao1'] = _chao1_richness(nonzero_counts)
            
            if 'ace' in metrics:
                sample_diversity['ace'] = _ace_richness(nonzero_counts)
        
        diversity_data.append(sample_diversity)
    
    diversity_df = pd.DataFrame(diversity_data, index=abundance_matrix.index)
    return diversity_df


def _shannon_diversity(counts: pd.Series) -> float:
    """Calculate Shannon diversity index."""
    proportions = counts / counts.sum()
    shannon = -np.sum(proportions * np.log(proportions))
    return shannon


def _simpson_diversity(counts: pd.Series) -> float:
    """Calculate Simpson diversity index."""
    proportions = counts / counts.sum()
    simpson = 1 - np.sum(proportions ** 2)
    return simpson


def _chao1_richness(counts: pd.Series) -> float:
    """Calculate Chao1 richness estimator."""
    observed_richness = len(counts)
    
    # Count singletons and doubletons
    singletons = (counts == 1).sum()
    doubletons = (counts == 2).sum()
    
    if doubletons > 0:
        chao1 = observed_richness + (singletons ** 2) / (2 * doubletons)
    else:
        # Modified formula when no doubletons
        chao1 = observed_richness + (singletons * (singletons - 1)) / 2
    
    return chao1


def _ace_richness(counts: pd.Series) -> float:
    """Calculate ACE (Abundance Coverage Estimator) richness."""
    # Separate abundant (>10) and rare (≤10) species
    abundant = counts[counts > 10]
    rare = counts[counts <= 10]
    
    s_abundant = len(abundant)
    s_rare = len(rare)
    
    if s_rare == 0:
        return s_abundant
    
    n_rare = rare.sum()
    
    # Calculate coverage
    f1 = (rare == 1).sum()  # singletons in rare
    if n_rare > 0:
        c_rare = 1 - f1 / n_rare
    else:
        c_rare = 1
    
    if c_rare > 0:
        ace = s_abundant + (s_rare / c_rare) + (f1 / c_rare) * max(0, np.sum(rare * (rare - 1)) / (n_rare * (n_rare - 1)) - 1)
    else:
        ace = s_abundant + s_rare
    
    return ace


def calculate_beta_diversity(abundance_matrix: pd.DataFrame, 
                           metric: str = "bray_curtis") -> pd.DataFrame:
    """
    Calculate beta diversity (dissimilarity) between samples.
    
    Args:
        abundance_matrix: DataFrame with samples as rows, taxa as columns
        metric: Distance metric ('bray_curtis', 'jaccard', 'euclidean', 'cosine')
        
    Returns:
        Square distance matrix
    """
    from scipy.spatial.distance import pdist, squareform
    
    if metric == "bray_curtis":
        distances = pdist(abundance_matrix.values, metric='braycurtis')
    elif metric == "jaccard":
        # Convert to presence/absence for Jaccard
        binary_matrix = (abundance_matrix > 0).astype(int)
        distances = pdist(binary_matrix.values, metric='jaccard')
    elif metric == "euclidean":
        distances = pdist(abundance_matrix.values, metric='euclidean')
    elif metric == "cosine":
        distances = pdist(abundance_matrix.values, metric='cosine')
    else:
        raise ValueError(f"Unknown distance metric: {metric}")
    
    # Convert to square matrix
    distance_matrix = squareform(distances)
    distance_df = pd.DataFrame(
        distance_matrix, 
        index=abundance_matrix.index, 
        columns=abundance_matrix.index
    )
    
    return distance_df


def filter_low_abundance_taxa(abundance_matrix: pd.DataFrame, 
                            min_abundance: float = 0.001,
                            min_prevalence: float = 0.1) -> pd.DataFrame:
    """
    Filter out low abundance and low prevalence taxa.
    
    Args:
        abundance_matrix: DataFrame with samples as rows, taxa as columns
        min_abundance: Minimum relative abundance threshold
        min_prevalence: Minimum prevalence (fraction of samples) threshold
        
    Returns:
        Filtered abundance matrix
    """
    # Convert to relative abundance
    relative_abundance = abundance_matrix.div(abundance_matrix.sum(axis=1), axis=0)
    
    # Calculate prevalence (fraction of samples with taxon present)
    prevalence = (relative_abundance > 0).sum(axis=0) / len(relative_abundance)
    
    # Calculate mean relative abundance
    mean_abundance = relative_abundance.mean(axis=0)
    
    # Filter taxa
    keep_taxa = (mean_abundance >= min_abundance) & (prevalence >= min_prevalence)
    
    filtered_matrix = abundance_matrix.loc[:, keep_taxa]
    
    logger.info(f"Filtered taxa: {abundance_matrix.shape[1]} -> {filtered_matrix.shape[1]}")
    return filtered_matrix


def generate_rarefaction_curve(abundance_matrix: pd.DataFrame, 
                              step_size: int = 1000) -> pd.DataFrame:
    """
    Generate rarefaction curves for samples.
    
    Args:
        abundance_matrix: DataFrame with samples as rows, taxa as columns
        step_size: Step size for rarefaction depths
        
    Returns:
        DataFrame with rarefaction curves (depths vs richness)
    """
    rarefaction_data = []
    
    for sample_id in abundance_matrix.index:
        sample_counts = abundance_matrix.loc[sample_id]
        total_reads = sample_counts.sum()
        
        if total_reads == 0:
            continue
        
        # Create read pool
        read_pool = []
        for taxon, count in sample_counts.items():
            read_pool.extend([taxon] * int(count))
        
        # Generate rarefaction curve
        max_depth = min(int(total_reads), 20000)  # Limit for computational efficiency
        depths = list(range(step_size, max_depth + 1, step_size))
        
        for depth in depths:
            # Randomly sample reads
            np.random.seed(42)
            sampled_reads = np.random.choice(read_pool, size=depth, replace=False)
            richness = len(set(sampled_reads))
            
            rarefaction_data.append({
                'sample_id': sample_id,
                'depth': depth,
                'richness': richness
            })
    
    rarefaction_df = pd.DataFrame(rarefaction_data)
    return rarefaction_df


def merge_abundance_tables(table1: pd.DataFrame, table2: pd.DataFrame, 
                          how: str = 'outer') -> pd.DataFrame:
    """
    Merge two abundance tables.
    
    Args:
        table1: First abundance table
        table2: Second abundance table
        how: How to handle missing values ('outer', 'inner')
        
    Returns:
        Merged abundance table
    """
    merged = pd.concat([table1, table2], axis=0, sort=True, join=how)
    
    # Fill NaN with 0
    merged = merged.fillna(0)
    
    logger.info(f"Merged tables: {table1.shape} + {table2.shape} -> {merged.shape}")
    return merged