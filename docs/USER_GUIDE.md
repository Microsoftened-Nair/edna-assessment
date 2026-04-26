# User Guide: Embeddings to Classification Workflow

This guide covers the current backend behavior:

- Upload FASTA
- Run pretrained DNABERT2
- Generate embedding artifacts
- Generate sequence-level classifications
- Render a detailed HTML web report
- Monitor progress in frontend

## 1. Start Backend

```bash
source virt/bin/activate
python -m edna_api.server
```

API base: `http://127.0.0.1:8000/api`

## 2. Start Frontend

```bash
cd frontend
npm run dev
```

## 3. Single Run

1. Open Single Run.
2. Upload a FASTA file.
3. Start analysis.
4. Watch progress updates while embeddings/classification/report stages complete.
5. Open run details and review classifications.
6. Open the HTML report and download artifacts as needed.

## 4. Batch Run

1. Open Batch Run.
2. Upload FASTA files for each sample.
3. Schedule batch.
4. Monitor per-sample progress/status.
5. Download artifacts after completion.

## 5. What Runs Under the Hood

- API receives run request.
- API worker invokes `run_pretrained_embeddings(...)`.
- `DNABERT2EmbeddingsExtractor.extract(...)` computes embeddings.
- `EmbeddingTaxonomyClassifier.classify_embeddings(...)` generates classifications.
- `create_classification_html_report(...)` renders the final report.
- API persists per-step progress and all output paths.

## 6. API Endpoints Used by Frontend

- `POST /api/auth/login`
- `POST /api/uploads`
- `POST /api/runs`
- `GET /api/runs/<run_id>`
- `GET /api/runs/recent`
- `POST /api/runs/batch`
- `GET /api/runs/batch/<batch_id>`
- `GET /api/dashboard`
- `GET /api/files`
- `GET /api/logs`

## 7. Output Artifacts

Each run writes a compressed NumPy archive (`.npz`) with:

- `sequence_ids`
- `embeddings`
- `model_name`
- `max_length`

Each run also writes classification/report artifacts:

- `{sample_id}_taxonomic_classifications.csv`
- `{sample_id}_taxonomic_classifications.json`
- `{sample_id}_classification_summary.json`
- `{sample_id}_classification_report.html`

## 8. Notes

- If a supervised classifier bundle is provided, taxonomy labels come from that bundle.
- Without a bundle, the system uses an unsupervised OTU-like fallback so reports still render.
