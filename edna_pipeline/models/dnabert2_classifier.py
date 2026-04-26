"""
DNABERT-2 Classifier for 16S Taxonomic Classification

This module provides a classifier that uses fine-tuned DNABERT-2 model
for species-level taxonomic classification of 16S rRNA sequences.

Usage:
    from edna_pipeline.models.dnabert2_classifier import DNABERT2Classifier
    
    classifier = DNABERT2Classifier(model_path="models/dnabert2_16s_species")
    result = classifier.predict("ACGT...")
"""

import os
import logging
import pickle
import importlib
import warnings
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union
import numpy as np

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, AutoModel, AutoConfig
    from transformers.dynamic_module_utils import get_class_from_dynamic_module
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from sklearn.preprocessing import LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

logger = logging.getLogger(__name__)

# Suppress a known non-actionable warning emitted by older hub internals.
warnings.filterwarnings(
    "ignore",
    message=r"`resume_download` is deprecated.*",
    category=FutureWarning,
    module=r"huggingface_hub\.file_download",
)


def _is_local_model_ref(model_ref: str) -> bool:
    """Return True when model_ref points to a local file system path."""
    return Path(model_ref).expanduser().exists()


def _get_hf_token(model_ref: str) -> Optional[str]:
    """
    Read Hugging Face token from environment for remote model loads.

    For local paths no token is required.
    """
    if _is_local_model_ref(model_ref):
        return None

    # Public models can be loaded without authentication; private/gated models
    # still require HF_TOKEN and will fail upstream with a clear Hugging Face error.
    token = os.getenv("HF_TOKEN")
    return token if token else None


def _ensure_tokenizer_pad_token(tokenizer) -> None:
    """Ensure tokenizer has a usable pad token/id for model config initialization."""
    if getattr(tokenizer, "pad_token_id", None) is not None:
        return

    for attr in ("eos_token", "sep_token", "cls_token", "unk_token"):
        candidate = getattr(tokenizer, attr, None)
        if candidate is not None:
            tokenizer.pad_token = candidate
            break

    if getattr(tokenizer, "pad_token_id", None) is None:
        tokenizer.pad_token_id = 0


def _should_fallback_without_remote_code(exc: Exception) -> bool:
    """Return True when we can safely retry without trust_remote_code."""
    msg = str(exc).lower()
    return (
        "einops" in msg
        or "requires the following packages" in msg
        or "config_class" in msg
        or "not consistent with the config class" in msg
        or "requires you to execute the configuration file" in msg
    )


def _load_remote_backbone_with_dynamic_class(
    model_name: str,
    hf_token: Optional[str],
    pad_token_id: int,
):
    """
    Load remote DNABERT-2 backbone by resolving the dynamic class directly.

    This avoids config-class mismatches that can occur between the locally
    imported transformers BertConfig class and the remote module's BertConfig.
    """
    config = AutoConfig.from_pretrained(
        model_name,
        token=hf_token,
        trust_remote_code=True,
    )
    model_cls_ref = getattr(config, "auto_map", {}).get("AutoModel")
    if not model_cls_ref:
        raise RuntimeError(f"AutoModel mapping not found for remote model '{model_name}'.")

    model_class = get_class_from_dynamic_module(
        model_cls_ref,
        model_name,
        token=hf_token,
    )

    # Align class-level config type to remote config type before loading.
    model_class.config_class = config.__class__

    # DNABERT-2 checkpoints are used for embeddings only here; pooler is unnecessary
    # and can trigger "newly initialized" noise in logs.
    if hasattr(config, "add_pooling_layer"):
        config.add_pooling_layer = False

    if getattr(config, "pad_token_id", None) is None:
        config.pad_token_id = pad_token_id

    return model_class.from_pretrained(
        model_name,
        token=hf_token,
        config=config,
        low_cpu_mem_usage=False,
    )


def _prefer_dynamic_loader(model_name: str) -> bool:
    """Use dynamic class loader first for known remote-code DNABERT-2 model IDs."""
    return (not _is_local_model_ref(model_name)) and ("dnabert-2" in model_name.lower())


def _disable_remote_flash_attention(model) -> None:
    """
    Disable DNABERT-2 Triton flash-attention path when loaded from remote code.

    Some Triton versions are incompatible with the DNABERT-2 custom kernel.
    For inference robustness we force the PyTorch attention path.
    """
    module_name = getattr(model.__class__, "__module__", "")
    if "transformers_modules" not in module_name:
        return

    try:
        model_module = importlib.import_module(module_name)
        if hasattr(model_module, "flash_attn_qkvpacked_func"):
            model_module.flash_attn_qkvpacked_func = None
            logger.info(
                "Disabled DNABERT-2 Triton flash attention for compatibility; using PyTorch attention backend."
            )
    except Exception as exc:
        logger.warning("Could not disable DNABERT-2 flash attention: %s", exc)


def _get_last_hidden_state(outputs):
    """Normalize transformer outputs and return the last hidden state tensor."""
    if hasattr(outputs, "last_hidden_state"):
        return outputs.last_hidden_state

    if isinstance(outputs, dict) and "last_hidden_state" in outputs:
        return outputs["last_hidden_state"]

    if isinstance(outputs, (tuple, list)) and len(outputs) > 0:
        return outputs[0]

    raise RuntimeError(
        f"Unsupported model output type for embedding extraction: {type(outputs)!r}"
    )


class DNABERT2Classifier:
    """
    DNABERT-2 based classifier for 16S taxonomic classification.
    
    Supports two modes:
    1. Full fine-tuned model: Uses DNABERT-2 with classification head
    2. Embeddings + Classifier: Extracts embeddings and uses simple classifier
    """
    
    def __init__(
        self,
        model_path: Union[str, Path],
        max_length: int = 256,
        device: Optional[str] = None,
        use_cuda: bool = True
    ):
        """
        Initialize DNABERT-2 classifier.
        
        Parameters:
        -----------
        model_path : str or Path
            Path to the fine-tuned model directory
        max_length : int
            Maximum sequence length for tokenization
        device : str, optional
            Device to use ('cuda' or 'cpu'). If None, auto-detect.
        use_cuda : bool
            Whether to use CUDA if available
        """
        self.model_path = Path(model_path)
        self.max_length = max_length
        
        if not TORCH_AVAILABLE:
            raise ImportError(
                "torch and transformers are required for DNABERT-2. "
                "Install with: pip install torch transformers"
            )
        
        # Set device
        if device:
            self.device = torch.device(device)
        elif use_cuda and torch.cuda.is_available():
            self.device = torch.device('cuda')
        else:
            self.device = torch.device('cpu')
        
        self.model = None
        self.tokenizer = None
        self.label_encoder = None
        self.model_info = None
        self.use_embeddings = False
        
        self._load_model()
    
    def _load_model(self):
        """Load the fine-tuned model and tokenizer."""
        if not self.model_path.exists():
            logger.warning(f"Model path {self.model_path} does not exist")
            return
        
        # Load tokenizer
        tokenizer_path = self.model_path / "tokenizer.json"
        if tokenizer_path.exists():
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(self.model_path),
                trust_remote_code=True,
            )
        else:
            # Try loading from original model
            logger.info("Tokenizer not found, loading from original DNABERT-2")
            base_model_name = "zhihan1996/DNABERT-2-117M"
            self.tokenizer = AutoTokenizer.from_pretrained(
                base_model_name,
                token=_get_hf_token(base_model_name),
                trust_remote_code=True,
            )
        
        # Load model
        config_path = self.model_path / "config.json"
        if config_path.exists():
            try:
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    str(self.model_path),
                    trust_remote_code=True,
                    low_cpu_mem_usage=False,
                )
                self.model = self.model.to(self.device)
                self.model.eval()
                logger.info("Loaded fine-tuned classification model")
            except Exception as e:
                logger.warning(f"Could not load classification model: {e}")
                self._load_embeddings_mode()
        else:
            self._load_embeddings_mode()
        
        # Load label encoder
        label_encoder_path = self.model_path / "label_encoder.pkl"
        if label_encoder_path.exists():
            with open(label_encoder_path, 'rb') as f:
                self.label_encoder = pickle.load(f)
        
        # Load model info
        info_path = self.model_path / "model_info.json"
        if info_path.exists():
            import json
            with open(info_path, 'r') as f:
                self.model_info = json.load(f)
    
    def _load_embeddings_mode(self):
        """Fallback to embeddings + classifier mode."""
        logger.info("Loading in embeddings mode...")
        self.use_embeddings = True
        
        # Load base encoder model for embeddings.
        base_model_name = "zhihan1996/DNABERT-2-117M"
        if self.tokenizer is not None:
            _ensure_tokenizer_pad_token(self.tokenizer)
        hf_token = _get_hf_token(base_model_name)
        if _prefer_dynamic_loader(base_model_name):
            self.model = _load_remote_backbone_with_dynamic_class(
                base_model_name,
                hf_token,
                getattr(self.tokenizer, "pad_token_id", 0),
            )
            _disable_remote_flash_attention(self.model)
            self.model = self.model.to(self.device)
            self.model.eval()
            return

        try:
            self.model = AutoModel.from_pretrained(
                base_model_name,
                token=hf_token,
                trust_remote_code=True,
                low_cpu_mem_usage=False,
                pad_token_id=getattr(self.tokenizer, "pad_token_id", 0),
                add_pooling_layer=False,
            )
        except Exception as exc:
            if not _should_fallback_without_remote_code(exc):
                raise
            logger.warning(
                "AutoModel remote load failed (%s). Retrying with dynamic class loader.",
                exc,
            )
            self.model = _load_remote_backbone_with_dynamic_class(
                base_model_name,
                hf_token,
                getattr(self.tokenizer, "pad_token_id", 0),
            )
        _disable_remote_flash_attention(self.model)
        self.model = self.model.to(self.device)
        self.model.eval()
    
    def _get_embeddings(self, sequences: List[str]) -> np.ndarray:
        """Extract embeddings from sequences."""
        embeddings = []
        
        for seq in sequences:
            # Truncate if too long
            seq = seq[:self.max_length]
            
            inputs = self.tokenizer(
                seq,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_length,
                padding=True
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # Use [CLS] token embedding or mean pooling
            hidden = _get_last_hidden_state(outputs)
            embedding = hidden.mean(dim=1).cpu().numpy()
            embeddings.append(embedding[0])
        
        return np.array(embeddings)
    
    def predict(self, sequence: str) -> Dict:
        """
        Predict taxonomy for a single sequence.
        
        Parameters:
        -----------
        sequence : str
            DNA sequence
            
        Returns:
        --------
        Dict with prediction results including:
        - species: Predicted species
        - genus: Predicted genus
        - family: Predicted family
        - confidence: Confidence score
        - method: 'dnabert2' or 'embeddings'
        """
        if self.model is None:
            return self._unclassified_result()
        
        if self.use_embeddings:
            # Use embeddings (requires trained classifier)
            logger.warning("Model is in embeddings mode - need to train classifier first")
            return self._unclassified_result()
        
        # Full model prediction
        inputs = self.tokenizer(
            sequence,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_length,
            padding=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        pred_idx = probs.argmax().item()
        confidence = probs.max().item()
        
        # Get species prediction
        if self.label_encoder:
            species = self.label_encoder.inverse_transform([pred_idx])[0]
        else:
            species = f"class_{pred_idx}"
        
        # Parse species to get genus/family
        parts = species.split()
        genus = parts[0] if len(parts) > 0 else "Unknown"
        species_full = " ".join(parts[:2]) if len(parts) > 1 else species
        
        return {
            "kingdom": "Bacteria",  # 16S is mostly bacterial
            "phylum": "Unknown",
            "class": "Unknown",
            "order": "Unknown",
            "family": "Unknown",
            "genus": genus,
            "species": species_full,
            "confidence": confidence * 100,
            "method": "dnabert2",
            "model_type": "transformer"
        }
    
    def predict_batch(self, sequences: List[str]) -> List[Dict]:
        """
        Predict taxonomy for multiple sequences.
        
        Parameters:
        -----------
        sequences : List[str]
            List of DNA sequences
            
        Returns:
        --------
        List of prediction dictionaries
        """
        results = []
        for seq in sequences:
            results.append(self.predict(seq))
        return results
    
    def _unclassified_result(self) -> Dict:
        """Return unclassified result."""
        return {
            "kingdom": "Unknown",
            "phylum": "Unknown",
            "class": "Unknown",
            "order": "Unknown",
            "family": "Unknown",
            "genus": "Unknown",
            "species": "Unknown",
            "confidence": 0.0,
            "method": "dnabert2",
            "model_type": "none"
        }
    
    @classmethod
    def train_from_embeddings(
        cls,
        model_path: Union[str, Path],
        embeddings: np.ndarray,
        labels: List[str],
        classifier_type: str = "logistic_regression",
        test_size: float = 0.2,
        **kwargs
    ) -> Dict:
        """
        Train a classifier on DNABERT-2 embeddings.
        
        Parameters:
        -----------
        model_path : str or Path
            Path to save the trained classifier
        embeddings : np.ndarray
            Pre-computed embeddings
        labels : List[str]
            Species labels
        classifier_type : str
            'logistic_regression' or 'random_forest'
        test_size : float
            Test set fraction
            
        Returns:
        --------
        Dict with training metrics
        """
        # Encode labels
        label_encoder = LabelEncoder()
        y = label_encoder.fit_transform(labels)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            embeddings, y, test_size=test_size, random_state=42, stratify=y
        )
        
        # Train classifier
        if classifier_type == "logistic_regression":
            classifier = LogisticRegression(max_iter=1000, **kwargs)
        else:
            classifier = RandomForestClassifier(n_estimators=100, **kwargs)
        
        classifier.fit(X_train, y_train)
        
        # Evaluate
        y_pred = classifier.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        
        # Save
        model_path = Path(model_path)
        model_path.mkdir(parents=True, exist_ok=True)
        
        with open(model_path / "classifier.pkl", 'wb') as f:
            pickle.dump(classifier, f)
        
        with open(model_path / "label_encoder.pkl", 'wb') as f:
            pickle.dump(label_encoder, f)
        
        import json
        with open(model_path / "model_info.json", 'w') as f:
            json.dump({
                "classifier_type": classifier_type,
                "accuracy": accuracy,
                "num_classes": len(label_encoder.classes_)
            }, f)
        
        return {"accuracy": accuracy, "num_classes": len(label_encoder.classes_)}


class DNABERT2EmbeddingsExtractor:
    """
    Extract embeddings from DNABERT-2 for downstream classification.
    """
    
    def __init__(
        self,
        model_name: str = "zhihan1996/DNABERT-2-117M",
        max_length: int = 256,
        device: Optional[str] = None
    ):
        """Initialize embeddings extractor."""
        if not TORCH_AVAILABLE:
            raise ImportError("torch and transformers required")
        
        if device:
            self.device = torch.device(device)
        else:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        self.max_length = max_length
        hf_token = _get_hf_token(model_name)
        
        logger.info(f"Loading DNABERT-2 from {model_name}")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                token=hf_token,
                trust_remote_code=True,
            )
            _ensure_tokenizer_pad_token(self.tokenizer)

            if _prefer_dynamic_loader(model_name):
                self.model = _load_remote_backbone_with_dynamic_class(
                    model_name,
                    hf_token,
                    self.tokenizer.pad_token_id,
                )
                _disable_remote_flash_attention(self.model)
                self.model = self.model.to(self.device)
                self.model.eval()
                return

            self.model = AutoModel.from_pretrained(
                model_name,
                token=hf_token,
                trust_remote_code=True,
                low_cpu_mem_usage=False,
                pad_token_id=self.tokenizer.pad_token_id,
                add_pooling_layer=False,
            )
            _disable_remote_flash_attention(self.model)
        except Exception as exc:
            if not _should_fallback_without_remote_code(exc):
                raise

            logger.warning(
                "Remote-code AutoModel load failed (%s). "
                "Retrying with dynamic class loader.",
                exc,
            )
            try:
                self.model = _load_remote_backbone_with_dynamic_class(
                    model_name,
                    hf_token,
                    self.tokenizer.pad_token_id,
                )
                _disable_remote_flash_attention(self.model)
            except Exception:
                # Final attempt: standard load without explicit config.
                self.tokenizer = AutoTokenizer.from_pretrained(
                    model_name,
                    token=hf_token,
                    trust_remote_code=False,
                )
                _ensure_tokenizer_pad_token(self.tokenizer)
                self.model = AutoModel.from_pretrained(
                    model_name,
                    token=hf_token,
                    trust_remote_code=False,
                    low_cpu_mem_usage=False,
                    add_pooling_layer=False,
                )
        self.model = self.model.to(self.device)
        self.model.eval()
    
    def extract(
        self,
        sequences: List[str],
        batch_size: int = 32,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> np.ndarray:
        """
        Extract embeddings for sequences.
        
        Parameters:
        -----------
        sequences : List[str]
            DNA sequences
        batch_size : int
            Batch size for processing
            
        Returns:
        --------
        np.ndarray of shape (n_sequences, embedding_dim)
        """
        all_embeddings = []
        
        total = len(sequences)
        for i in range(0, total, batch_size):
            batch = sequences[i:i+batch_size]
            
            # Truncate sequences
            batch = [seq[:self.max_length] for seq in batch]
            
            inputs = self.tokenizer(
                batch,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_length,
                padding=True
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # Mean pooling
            hidden = _get_last_hidden_state(outputs)
            embeddings = hidden.mean(dim=1).cpu().numpy()
            all_embeddings.append(embeddings)

            if progress_callback is not None:
                processed = min(i + len(batch), total)
                progress_callback(processed, total)
        
        return np.vstack(all_embeddings)
    
    def save_embeddings(self, embeddings: np.ndarray, path: Union[str, Path]):
        """Save embeddings to file."""
        np.save(path, embeddings)
    
    def load_embeddings(self, path: Union[str, Path]) -> np.ndarray:
        """Load embeddings from file."""
        return np.load(path)
