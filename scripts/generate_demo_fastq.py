#!/usr/bin/env python3
"""Utility to generate synthetic FASTQ fixtures for frontend and API testing."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import List

NUCLEOTIDES = "ACGT"
DEFAULT_QUALITY = "I"


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create demo FASTQ files for manual testing.")
    parser.add_argument("--output-dir", default="data/demo_fastq", help="Directory to write FASTQ files")
    parser.add_argument("--single", type=int, default=2, help="Number of single-end samples to generate")
    parser.add_argument("--paired", type=int, default=3, help="Number of paired-end samples to generate")
    parser.add_argument("--reads-per-file", type=int, default=25, help="Reads to include in every FASTQ file")
    parser.add_argument("--read-length", type=int, default=150, help="Length of each synthetic read")
    parser.add_argument("--seed", type=int, default=7, help="Seed for deterministic sequence generation")
    return parser.parse_args()


def random_read(read_length: int) -> str:
    return "".join(random.choices(NUCLEOTIDES, k=read_length))


def quality_string(read_length: int) -> str:
    return DEFAULT_QUALITY * read_length


def write_fastq(path: Path, reads: List[str]) -> None:
    with path.open("w", encoding="ascii") as handle:
        for idx, sequence in enumerate(reads, start=1):
            handle.write(f"@read_{idx}\n{sequence}\n+\n{quality_string(len(sequence))}\n")


def generate_reads(count: int, read_length: int) -> List[str]:
    return [random_read(read_length) for _ in range(count)]


def main() -> None:
    args = build_args()
    random.seed(args.seed)

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"single": [], "paired": []}

    for idx in range(1, args.single + 1):
        sample_id = f"sample_single_{idx:02d}"
        file_path = output_dir / f"{sample_id}.fastq"
        write_fastq(file_path, generate_reads(args.reads_per_file, args.read_length))
        manifest["single"].append({"sample_id": sample_id, "file": str(file_path.resolve())})

    for idx in range(1, args.paired + 1):
        sample_id = f"sample_paired_{idx:02d}"
        forward_path = output_dir / f"{sample_id}_R1.fastq"
        reverse_path = output_dir / f"{sample_id}_R2.fastq"
        reads_r1 = generate_reads(args.reads_per_file, args.read_length)
        reads_r2 = generate_reads(args.reads_per_file, args.read_length)
        write_fastq(forward_path, reads_r1)
        write_fastq(reverse_path, reads_r2)
        manifest["paired"].append(
            {
                "sample_id": sample_id,
                "forward": str(forward_path.resolve()),
                "reverse": str(reverse_path.resolve()),
            }
        )

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("Generated FASTQ fixtures:")
    for record in manifest["single"]:
        print(f"  • {record['sample_id']} -> {record['file']}")
    for record in manifest["paired"]:
        print(f"  • {record['sample_id']} -> {record['forward']}, {record['reverse']}")
    print(f"Manifest: {manifest_path.resolve()}")


if __name__ == "__main__":
    main()
