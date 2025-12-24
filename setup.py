#!/usr/bin/env python3
"""Setup script for the AI-driven deep-sea eDNA analysis pipeline."""

from setuptools import setup, find_packages
import os


def read_requirements():
    """Read requirements from requirements.txt."""
    requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    with open(requirements_path, 'r') as f:
        requirements = []
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                # Remove version constraints for problematic packages
                if 'sqlite3' in line or line.startswith('multiprocessing') or line.startswith('concurrent.futures'):
                    continue
                requirements.append(line)
    return requirements


def read_long_description():
    """Read long description from README.md."""
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    with open(readme_path, 'r', encoding='utf-8') as f:
        return f.read()


setup(
    name="deep-sea-edna-pipeline",
    version="1.0.0",
    author="Deep-Sea eDNA Analysis Team",
    author_email="contact@deep-sea-edna.org",
    description="AI-driven deep-sea eDNA analysis pipeline for eukaryotic biodiversity assessment",
    long_description=read_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/deep-sea-edna-pipeline",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=7.1.0",
            "pytest-cov>=3.0.0",
            "black>=22.0.0",
            "flake8>=4.0.0",
            "mypy>=0.971",
        ],
        "docs": [
            "sphinx>=5.0.0",
            "sphinx-rtd-theme>=1.0.0",
            "nbsphinx>=0.8.0",
        ],
        "gpu": [
            "cupy-cuda11x>=10.6.0",  # Adjust CUDA version as needed
        ],
    },
    entry_points={
        "console_scripts": [
            "edna-pipeline=edna_pipeline.cli:main",
        ],
    },
    package_data={
        "edna_pipeline": [
            "config/*.yaml",
            "data/*.json",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    keywords=[
        "bioinformatics",
        "environmental DNA",
        "deep learning",
        "taxonomy",
        "biodiversity",
        "marine biology",
        "sequence analysis",
    ],
    project_urls={
        "Bug Reports": "https://github.com/your-org/deep-sea-edna-pipeline/issues",
        "Source": "https://github.com/your-org/deep-sea-edna-pipeline",
        "Documentation": "https://deep-sea-edna-pipeline.readthedocs.io/",
    },
)