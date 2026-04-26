#!/usr/bin/env python3
"""Run pretrained DNABERT-2 embedding inference without fine-tuning."""

import argparse
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

import numpy as np
from Bio import SeqIO

# Ensure project root is importable when running script directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from edna_pipeline.models.dnabert2_classifier import DNABERT2EmbeddingsExtractor


def run_pretrained_embeddings(
    input_fasta: str,
    output: str = "results/dnabert2_pretrained_embeddings.npz",
    model_name: str = "zhihan1996/DNABERT-2-117M",
    max_length: int = 256,
    batch_size: int = 16,
    device: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, object]:
    """Run pretrained DNABERT-2 embeddings extraction and save NPZ output."""
    records = list(SeqIO.parse(input_fasta, "fasta"))
    if not records:
        raise ValueError(f"No FASTA records found in {input_fasta}")

    sequence_ids = [record.id for record in records]
    sequences = [str(record.seq) for record in records]

    extractor = DNABERT2EmbeddingsExtractor(
        model_name=model_name,
        max_length=max_length,
        device=device,
    )
    embeddings = extractor.extract(
        sequences,
        batch_size=batch_size,
        progress_callback=progress_callback,
    )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        sequence_ids=np.array(sequence_ids),
        embeddings=embeddings,
        model_name=np.array([model_name]),
        max_length=np.array([max_length]),
    )

    return {
        "num_sequences": len(sequence_ids),
        "embedding_shape": tuple(embeddings.shape),
        "output_path": str(output_path),
        "model_name": model_name,
        "max_length": max_length,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract DNABERT-2 embeddings from a FASTA file (no fine-tuning)."
    )
    parser.add_argument("--input-fasta", required=True, help="Input FASTA file with DNA sequences")
    parser.add_argument(
        "--output",
        default="results/dnabert2_pretrained_embeddings.npz",
        help="Output .npz file path (default: results/dnabert2_pretrained_embeddings.npz)",
    )
    parser.add_argument(
        "--model-name",
        default="zhihan1996/DNABERT-2-117M",
        help="Hugging Face model ID (default: zhihan1996/DNABERT-2-117M)",
    )
    parser.add_argument("--max-length", type=int, default=256, help="Max token length")
    parser.add_argument("--batch-size", type=int, default=16, help="Inference batch size")
    parser.add_argument(
        "--device",
        default=None,
        help="Torch device, e.g. cpu or cuda. Defaults to auto-detect.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    result = run_pretrained_embeddings(
        input_fasta=args.input_fasta,
        output=args.output,
        model_name=args.model_name,
        max_length=args.max_length,
        batch_size=args.batch_size,
        device=args.device,
    )

    print(f"Saved embeddings for {result['num_sequences']} sequences")
    print(f"Embedding shape: {result['embedding_shape']}")
    print(f"Output: {result['output_path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
