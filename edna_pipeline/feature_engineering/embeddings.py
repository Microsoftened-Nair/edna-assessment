"""Sequence embedding methods for DNA sequences."""

import numpy as np
from typing import List, Dict, Union, Optional
from Bio.SeqRecord import SeqRecord
import logging
from collections import defaultdict
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
import umap

logger = logging.getLogger(__name__)


class SequenceEmbedder:
    """Create embeddings for DNA sequences using various methods."""
    
    def __init__(self, config: Dict):
        """
        Initialize sequence embedder.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.embedding_dim = config.get("embedding_dim", 128)
        self.kmer_size = config.get("embedding_kmer_size", 4)
        self.window_size = config.get("embedding_window_size", 5)
        self.min_count = config.get("embedding_min_count", 1)
        self.use_pretrained = config.get("use_pretrained_embeddings", False)
        
        # Trained embeddings
        self.kmer_embeddings = None
        self.embedding_vocabulary = None
        self.is_fitted = False
        
        logger.info(f"Initialized sequence embedder with dim={self.embedding_dim}")
    
    def _extract_kmers_for_embedding(self, sequence: str) -> List[str]:
        """Extract k-mers for embedding training."""
        sequence = sequence.upper()
        kmers = []
        
        for i in range(len(sequence) - self.kmer_size + 1):
            kmer = sequence[i:i+self.kmer_size]
            # Only include k-mers with valid nucleotides
            if all(base in 'ACGT' for base in kmer):
                kmers.append(kmer)
        
        return kmers
    
    def _build_vocabulary(self, sequences: List[Union[str, SeqRecord]]) -> Dict[str, int]:
        """Build k-mer vocabulary from sequences."""
        kmer_counts = defaultdict(int)
        
        for seq in sequences:
            seq_str = str(seq.seq) if isinstance(seq, SeqRecord) else str(seq)
            kmers = self._extract_kmers_for_embedding(seq_str)
            
            for kmer in kmers:
                kmer_counts[kmer] += 1
        
        # Filter by minimum count
        vocabulary = {}
        vocab_index = 0
        for kmer, count in kmer_counts.items():
            if count >= self.min_count:
                vocabulary[kmer] = vocab_index
                vocab_index += 1
        
        logger.info(f"Built vocabulary with {len(vocabulary)} k-mers")
        return vocabulary
    
    def _train_word2vec_style(self, sequences: List[Union[str, SeqRecord]]) -> np.ndarray:
        """
        Train Word2Vec-style embeddings for k-mers.
        Note: This is a simplified implementation. For production use,
        consider using gensim's Word2Vec or similar libraries.
        """
        # Build vocabulary
        self.embedding_vocabulary = self._build_vocabulary(sequences)
        vocab_size = len(self.embedding_vocabulary)
        
        if vocab_size == 0:
            logger.warning("Empty vocabulary, returning zero embeddings")
            return np.zeros((1, self.embedding_dim))
        
        # Initialize embeddings randomly
        embeddings = np.random.normal(0, 0.1, (vocab_size, self.embedding_dim))
        
        # Simple co-occurrence based training (simplified Skip-gram approach)
        learning_rate = 0.01
        epochs = 5
        
        for epoch in range(epochs):
            total_loss = 0
            n_updates = 0
            
            for seq in sequences:
                seq_str = str(seq.seq) if isinstance(seq, SeqRecord) else str(seq)
                kmers = self._extract_kmers_for_embedding(seq_str)
                
                # Create training examples
                for i, center_kmer in enumerate(kmers):
                    if center_kmer not in self.embedding_vocabulary:
                        continue
                    
                    center_idx = self.embedding_vocabulary[center_kmer]
                    
                    # Get context k-mers within window
                    start = max(0, i - self.window_size)
                    end = min(len(kmers), i + self.window_size + 1)
                    
                    for j in range(start, end):
                        if i == j:  # Skip center word
                            continue
                        
                        context_kmer = kmers[j]
                        if context_kmer not in self.embedding_vocabulary:
                            continue
                        
                        context_idx = self.embedding_vocabulary[context_kmer]
                        
                        # Simple update rule (simplified)
                        # In practice, you'd use hierarchical softmax or negative sampling
                        center_embed = embeddings[center_idx]
                        context_embed = embeddings[context_idx]
                        
                        # Compute similarity
                        similarity = np.dot(center_embed, context_embed)
                        
                        # Simple gradient update
                        grad = learning_rate * (1 - similarity)
                        embeddings[center_idx] += grad * context_embed
                        embeddings[context_idx] += grad * center_embed
                        
                        total_loss += (1 - similarity) ** 2
                        n_updates += 1
            
            if n_updates > 0:
                avg_loss = total_loss / n_updates
                logger.debug(f"Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.4f}")
        
        logger.info(f"Trained embeddings for {vocab_size} k-mers")
        return embeddings
    
    def _sequence_to_embedding(self, sequence: str) -> np.ndarray:
        """Convert a sequence to an embedding vector."""
        if not self.is_fitted:
            raise ValueError("Embedder must be fitted before use")
        
        kmers = self._extract_kmers_for_embedding(sequence)
        
        if not kmers:
            return np.zeros(self.embedding_dim)
        
        # Get embeddings for k-mers in the sequence
        kmer_embeddings = []
        for kmer in kmers:
            if kmer in self.embedding_vocabulary:
                idx = self.embedding_vocabulary[kmer]
                kmer_embeddings.append(self.kmer_embeddings[idx])
        
        if not kmer_embeddings:
            return np.zeros(self.embedding_dim)
        
        # Aggregate k-mer embeddings (mean pooling)
        sequence_embedding = np.mean(kmer_embeddings, axis=0)
        return sequence_embedding
    
    def fit_embeddings(self, sequences: List[Union[str, SeqRecord]]) -> 'SequenceEmbedder':
        """
        Fit embedding model on sequences.
        
        Args:
            sequences: List of sequences
            
        Returns:
            Self for method chaining
        """
        logger.info(f"Fitting embeddings on {len(sequences)} sequences")
        
        # Train embeddings
        self.kmer_embeddings = self._train_word2vec_style(sequences)
        self.is_fitted = True
        
        return self
    
    def transform_sequences(self, sequences: List[Union[str, SeqRecord]]) -> Dict[str, np.ndarray]:
        """
        Transform sequences to embedding representations.
        
        Args:
            sequences: List of sequences
            
        Returns:
            Dictionary with embedding features
        """
        # Fit embeddings if not already fitted
        if not self.is_fitted:
            self.fit_embeddings(sequences)
        
        # Convert sequences to embeddings
        embeddings = []
        for seq in sequences:
            seq_str = str(seq.seq) if isinstance(seq, SeqRecord) else str(seq)
            embedding = self._sequence_to_embedding(seq_str)
            embeddings.append(embedding)
        
        embedding_matrix = np.array(embeddings)
        
        logger.info(f"Generated embeddings: {embedding_matrix.shape}")
        
        return {"embeddings": embedding_matrix}
    
    def get_kmer_embeddings(self) -> Optional[Dict[str, np.ndarray]]:
        """
        Get k-mer embeddings as dictionary.
        
        Returns:
            Dictionary mapping k-mers to their embeddings
        """
        if not self.is_fitted:
            return None
        
        kmer_embed_dict = {}
        for kmer, idx in self.embedding_vocabulary.items():
            kmer_embed_dict[kmer] = self.kmer_embeddings[idx]
        
        return kmer_embed_dict
    
    def find_similar_kmers(self, kmer: str, top_k: int = 10) -> List[tuple]:
        """
        Find k-mers most similar to a given k-mer.
        
        Args:
            kmer: Query k-mer
            top_k: Number of similar k-mers to return
            
        Returns:
            List of (k-mer, similarity_score) tuples
        """
        if not self.is_fitted or kmer not in self.embedding_vocabulary:
            return []
        
        query_idx = self.embedding_vocabulary[kmer]
        query_embedding = self.kmer_embeddings[query_idx]
        
        # Calculate cosine similarities
        similarities = []
        for other_kmer, other_idx in self.embedding_vocabulary.items():
            if other_kmer == kmer:
                continue
            
            other_embedding = self.kmer_embeddings[other_idx]
            
            # Cosine similarity
            similarity = np.dot(query_embedding, other_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(other_embedding)
            )
            
            similarities.append((other_kmer, similarity))
        
        # Sort by similarity and return top k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def visualize_embeddings(self, method: str = "umap", n_components: int = 2) -> np.ndarray:
        """
        Reduce embedding dimensionality for visualization.
        
        Args:
            method: Dimensionality reduction method ("pca", "tsne", "umap")
            n_components: Number of output dimensions
            
        Returns:
            Reduced embeddings for visualization
        """
        if not self.is_fitted:
            raise ValueError("Embedder must be fitted before visualization")
        
        if method == "pca":
            reducer = PCA(n_components=n_components)
        elif method == "tsne":
            reducer = TSNE(n_components=n_components, random_state=42)
        elif method == "umap":
            reducer = umap.UMAP(n_components=n_components, random_state=42)
        else:
            raise ValueError(f"Unknown reduction method: {method}")
        
        reduced_embeddings = reducer.fit_transform(self.kmer_embeddings)
        
        logger.info(f"Reduced embeddings to {reduced_embeddings.shape} using {method}")
        return reduced_embeddings
    
    def save_embeddings(self, output_path: str):
        """Save trained embeddings to file."""
        if not self.is_fitted:
            raise ValueError("No embeddings to save")
        
        import pickle
        
        embedding_data = {
            "kmer_embeddings": self.kmer_embeddings,
            "vocabulary": self.embedding_vocabulary,
            "config": {
                "embedding_dim": self.embedding_dim,
                "kmer_size": self.kmer_size,
                "window_size": self.window_size,
                "min_count": self.min_count
            }
        }
        
        with open(output_path, 'wb') as f:
            pickle.dump(embedding_data, f)
        
        logger.info(f"Saved embeddings to {output_path}")
    
    def load_embeddings(self, input_path: str):
        """Load pre-trained embeddings from file."""
        import pickle
        
        try:
            with open(input_path, 'rb') as f:
                embedding_data = pickle.load(f)
            
            self.kmer_embeddings = embedding_data["kmer_embeddings"]
            self.embedding_vocabulary = embedding_data["vocabulary"]
            
            # Update config if available
            if "config" in embedding_data:
                config = embedding_data["config"]
                self.embedding_dim = config.get("embedding_dim", self.embedding_dim)
                self.kmer_size = config.get("kmer_size", self.kmer_size)
                self.window_size = config.get("window_size", self.window_size)
                self.min_count = config.get("min_count", self.min_count)
            
            self.is_fitted = True
            logger.info(f"Loaded embeddings from {input_path}")
            
        except Exception as e:
            logger.error(f"Failed to load embeddings: {e}")
            raise
    
    def get_embedding_statistics(self) -> Dict[str, float]:
        """Get statistics about the trained embeddings."""
        if not self.is_fitted:
            return {}
        
        stats = {
            "vocabulary_size": len(self.embedding_vocabulary),
            "embedding_dimension": self.embedding_dim,
            "kmer_size": self.kmer_size,
            "mean_embedding_norm": np.mean(np.linalg.norm(self.kmer_embeddings, axis=1)),
            "std_embedding_norm": np.std(np.linalg.norm(self.kmer_embeddings, axis=1))
        }
        
        return stats