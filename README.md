# eDNA DNABERT2 Classification Backend

This repository now supports an end-to-end backend workflow:

1. Upload FASTA files.
2. Start single or batch runs.
3. Run pretrained DNABERT2 inference.
4. Generate and store embeddings (`.npz`).
5. Convert embeddings into sequence-level classifications.
6. Generate a professional HTML report and structured JSON/CSV outputs.
7. Track live run progress from the frontend.

## Backend Flow

- Frontend uploads FASTA to the API.
- API schedules a run (single or batch).
- Run worker calls `scripts/run_pretrained_dnabert2.py`.
- Script uses `DNABERT2EmbeddingsExtractor` from `edna_pipeline/models/dnabert2_classifier.py`.
- API classifies embeddings using `EmbeddingTaxonomyClassifier`.
- API generates HTML report with `create_classification_html_report`.
- Artifacts and run status are updated with per-step progress.

## Minimal Backend Components

- `edna_api/server.py`: run orchestration API.
- `scripts/run_pretrained_dnabert2.py`: standalone embeddings runner.
- `edna_pipeline/models/dnabert2_classifier.py`: DNABERT2 embeddings extractor.
- `edna_pipeline/taxonomy/embedding_classifier.py`: post-embedding classification module.
- `edna_pipeline/visualization/classification_report.py`: HTML report renderer.

## Run Backend

```bash
source virt/bin/activate
python -m edna_api.server
```

Backend default URL: `http://127.0.0.1:8000`

## Run Frontend

```bash
cd frontend
npm run dev
```

Frontend API base should be `http://127.0.0.1:8000/api`.

## Active API Endpoints

- `POST /api/auth/login`
- `GET /api/health`
- `POST /api/uploads`
- `POST /api/runs`
- `GET /api/runs/<run_id>`
- `GET /api/runs/recent`
- `POST /api/runs/batch`
- `GET /api/runs/batch/<batch_id>`
- `GET /api/dashboard`
- `GET /api/files`
- `GET /api/logs`

## Run Outputs

Each completed run writes:

- Embeddings: `data/api/embeddings/<sample_id>_dnabert2_embeddings.npz`
- Classification CSV: `data/api/classifications/<sample_id>_taxonomic_classifications.csv`
- Classification JSON: `data/api/classifications/<sample_id>_taxonomic_classifications.json`
- Classification summary: `data/api/classifications/<sample_id>_classification_summary.json`
- HTML report: `data/api/reports/<sample_id>_classification_report.html`

NPZ keys:

- `sequence_ids`
- `embeddings`
- `model_name`
- `max_length`

Classification mode:

- If a supervised model bundle is provided via `configOverrides.classification.model_bundle`, predictions use that bundle.
- Otherwise, a deterministic unsupervised OTU-like fallback is used so classification artifacts are still produced.

## Script-Only Usage

You can run embeddings extraction directly without the API:

```bash
source virt/bin/activate
python scripts/run_pretrained_dnabert2.py \
  --input-fasta path/to/input.fasta \
  --output results/dnabert2_pretrained_embeddings.npz
```
