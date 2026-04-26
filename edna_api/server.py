import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

from edna_pipeline.taxonomy import EmbeddingTaxonomyClassifier
from edna_pipeline.visualization import create_classification_html_report
from scripts.run_pretrained_dnabert2 import run_pretrained_embeddings

BASE_DATA_DIR = Path("data/api")
RUNS_DIR = BASE_DATA_DIR / "runs"
BATCH_DIR = BASE_DATA_DIR / "batches"
LOG_DIR = BASE_DATA_DIR / "logs"
UPLOAD_DIR = BASE_DATA_DIR / "uploads"
EMBEDDINGS_DIR = BASE_DATA_DIR / "embeddings"
CLASSIFICATIONS_DIR = BASE_DATA_DIR / "classifications"
REPORTS_DIR = BASE_DATA_DIR / "reports"

for directory in (
    RUNS_DIR,
    BATCH_DIR,
    LOG_DIR,
    UPLOAD_DIR,
    EMBEDDINGS_DIR,
    CLASSIFICATIONS_DIR,
    REPORTS_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("edna_api")
logger.setLevel(logging.INFO)
if not any(isinstance(h, logging.FileHandler) and Path(h.baseFilename) == (LOG_DIR / "api.log") for h in logger.handlers):
    handler = logging.FileHandler(LOG_DIR / "api.log")
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

ALLOWED_FILE_ROOTS = [
    (Path.cwd() / "results").resolve(),
    BASE_DATA_DIR.resolve(),
]

ALLOWED_FASTA_SUFFIXES = {".fasta", ".fa", ".fna", ".fasta.gz", ".fa.gz", ".fna.gz"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _is_allowed_upload(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in ALLOWED_FASTA_SUFFIXES)


def _normalize_run_status(status: Optional[str], success: bool) -> str:
    if status:
        return status
    return "completed" if success else "failed"


class EmbeddingRunManager:
    def __init__(self, max_workers: int = 2):
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.batches: Dict[str, Dict[str, Any]] = {}
        self.futures: Dict[str, Any] = {}
        self.batch_futures: Dict[str, Any] = {}
        self._load_state()

    def _run_path(self, run_id: str) -> Path:
        return RUNS_DIR / f"{run_id}.json"

    def _batch_path(self, batch_id: str) -> Path:
        return BATCH_DIR / f"{batch_id}.json"

    def _load_state(self) -> None:
        for path in RUNS_DIR.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    run = json.load(handle)
                if isinstance(run, dict) and run.get("sample_id"):
                    self.runs[run["sample_id"]] = run
            except Exception as exc:
                logger.warning("Failed loading run state %s: %s", path, exc)

        for path in BATCH_DIR.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    batch = json.load(handle)
                if isinstance(batch, dict) and batch.get("batch_id"):
                    self.batches[batch["batch_id"]] = batch
            except Exception as exc:
                logger.warning("Failed loading batch state %s: %s", path, exc)

    def _persist_run(self, run: Dict[str, Any]) -> None:
        with open(self._run_path(run["sample_id"]), "w", encoding="utf-8") as handle:
            json.dump(run, handle, indent=2)

    def _persist_batch(self, batch: Dict[str, Any]) -> None:
        with open(self._batch_path(batch["batch_id"]), "w", encoding="utf-8") as handle:
            json.dump(batch, handle, indent=2)

    def _ensure_unique_run_id(self, base_id: str) -> str:
        with self.lock:
            if base_id not in self.runs:
                return base_id
            suffix = 1
            while f"{base_id}-{suffix}" in self.runs:
                suffix += 1
            return f"{base_id}-{suffix}"

    def _new_run_record(self, run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        output_dir = payload.get("configOverrides", {}).get("output.dir") or str(EMBEDDINGS_DIR)
        run = {
            "sample_id": run_id,
            "input_type": payload.get("inputType", "single"),
            "input_files": _to_list(payload.get("files")),
            "output_dir": str(output_dir),
            "start_time": _iso_now(),
            "end_time": None,
            "processing_time": None,
            "success": False,
            "error": None,
            "status": "queued",
            "pipeline_steps": [
                {
                    "step": "embedding_generation",
                    "status": "pending",
                    "results": {"message": "Queued for DNABERT2 embedding generation"},
                },
                {
                    "step": "taxonomic_classification",
                    "status": "pending",
                    "results": {"message": "Waiting for embeddings"},
                },
                {
                    "step": "report_generation",
                    "status": "pending",
                    "results": {"message": "Waiting for classification outputs"},
                }
            ],
            "current_step": "queued",
            "current_message": "Run queued",
            "progress": 0,
        }
        return run

    def _update_run(
        self,
        run_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        current_step: Optional[str] = None,
        current_message: Optional[str] = None,
        step_name: Optional[str] = None,
        step_status: Optional[str] = None,
        step_message: Optional[str] = None,
        step_results: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        finished: bool = False,
        success: Optional[bool] = None,
        end_time: Optional[str] = None,
        processing_time: Optional[float] = None,
    ) -> None:
        with self.lock:
            run = self.runs[run_id]
            if status is not None:
                run["status"] = status
            if progress is not None:
                run["progress"] = max(0, min(100, int(progress)))
            if current_step is not None:
                run["current_step"] = current_step
            if current_message is not None:
                run["current_message"] = current_message
            if error is not None:
                run["error"] = error
            if success is not None:
                run["success"] = success
            if processing_time is not None:
                run["processing_time"] = processing_time
            if end_time is not None:
                run["end_time"] = end_time
            elif finished:
                run["end_time"] = _iso_now()

            if run.get("pipeline_steps"):
                step = None
                if step_name:
                    for candidate in run["pipeline_steps"]:
                        if candidate.get("step") == step_name:
                            step = candidate
                            break
                if step is None:
                    step = run["pipeline_steps"][0]

                if step_status is not None:
                    step["status"] = step_status
                if step_message is not None:
                    results = step.setdefault("results", {})
                    if isinstance(results, dict):
                        results["message"] = step_message
                if step_results:
                    results = step.setdefault("results", {})
                    if isinstance(results, dict):
                        results.update(step_results)

            self._persist_run(run)

    def _execute_embedding_run(self, run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        start_ts = datetime.now(timezone.utc)
        files = _to_list(payload.get("files"))
        if not files:
            raise ValueError("No input FASTA file provided")

        fasta_path = Path(files[0])
        if not fasta_path.is_absolute():
            fasta_path = (Path.cwd() / fasta_path).resolve()
        else:
            fasta_path = fasta_path.resolve()

        if not fasta_path.exists():
            raise FileNotFoundError(f"Input file not found: {fasta_path}")

        output_dir = payload.get("configOverrides", {}).get("output.dir") or str(EMBEDDINGS_DIR)
        output_dir_path = Path(output_dir)
        if not output_dir_path.is_absolute():
            output_dir_path = (Path.cwd() / output_dir_path).resolve()
        output_dir_path.mkdir(parents=True, exist_ok=True)

        output_file = output_dir_path / f"{run_id}_dnabert2_embeddings.npz"
        model_name = payload.get("configOverrides", {}).get("model.name", "zhihan1996/DNABERT-2-117M")
        max_length = int(payload.get("configOverrides", {}).get("max.length", 256))
        batch_size = int(payload.get("configOverrides", {}).get("batch.size", 16))
        device = payload.get("configOverrides", {}).get("device")

        self._update_run(
            run_id,
            status="running",
            progress=10,
            current_step="embedding_generation",
            current_message="Loading pretrained DNABERT2 model",
            step_name="embedding_generation",
            step_status="running",
            step_message="Initializing model",
        )

        def _progress_callback(processed: int, total: int) -> None:
            if total <= 0:
                return
            ratio = processed / total
            progress = 20 + int(ratio * 75)
            self._update_run(
                run_id,
                status="running",
                progress=progress,
                current_step="embedding_generation",
                current_message=f"Generating embeddings ({processed}/{total} sequences)",
                step_name="embedding_generation",
                step_status="running",
                step_message=f"Processed {processed}/{total} sequences",
            )

        result = run_pretrained_embeddings(
            input_fasta=str(fasta_path),
            output=str(output_file),
            model_name=model_name,
            max_length=max_length,
            batch_size=batch_size,
            device=device,
            progress_callback=_progress_callback,
        )

        duration = (datetime.now(timezone.utc) - start_ts).total_seconds()
        self._update_run(
            run_id,
            status="running",
            progress=55,
            current_step="embedding_generation",
            current_message="DNABERT2 embedding generation completed",
            step_name="embedding_generation",
            step_status="completed",
            step_message="Embeddings generated successfully",
            step_results={
                "dnabert2_embeddings_file": result["output_path"],
                "total_classified": int(result["num_sequences"]),
                "embedding_shape": list(result["embedding_shape"]),
                "model_name": result["model_name"],
                "max_length": int(result["max_length"]),
            },
        )

        self._update_run(
            run_id,
            status="running",
            progress=65,
            current_step="taxonomic_classification",
            current_message="Classifying embeddings into taxonomic labels",
            step_name="taxonomic_classification",
            step_status="running",
            step_message="Running embedding classifier",
        )

        classification_output_dir = payload.get("configOverrides", {}).get("classification.output_dir") or str(
            CLASSIFICATIONS_DIR
        )
        model_bundle_path = payload.get("configOverrides", {}).get("classification.model_bundle")
        confidence_threshold = float(
            payload.get("configOverrides", {}).get("classification.confidence_threshold", 0.0)
        )

        classifier = EmbeddingTaxonomyClassifier(
            model_bundle_path=model_bundle_path,
            confidence_threshold=confidence_threshold,
        )
        classification_result = classifier.classify_embeddings(
            embeddings_file=result["output_path"],
            output_dir=classification_output_dir,
            sample_id=run_id,
        )

        self._update_run(
            run_id,
            status="running",
            progress=82,
            current_step="taxonomic_classification",
            current_message="Taxonomic classification completed",
            step_name="taxonomic_classification",
            step_status="completed",
            step_message="Classification generated successfully",
            step_results=classification_result,
        )

        self._update_run(
            run_id,
            status="running",
            progress=90,
            current_step="report_generation",
            current_message="Building HTML classification report",
            step_name="report_generation",
            step_status="running",
            step_message="Rendering report template",
        )

        report_output_dir = payload.get("configOverrides", {}).get("report.output_dir") or str(REPORTS_DIR)
        report_output_path = Path(report_output_dir) / f"{run_id}_classification_report.html"

        predictions_file = classification_result.get("predictions_file")
        predictions: List[Dict[str, Any]] = []
        if predictions_file:
            with open(predictions_file, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
                if isinstance(loaded, list):
                    predictions = loaded

        report_file = create_classification_html_report(
            report_path=str(report_output_path),
            sample_id=run_id,
            run_meta={
                "start_time": self.runs[run_id].get("start_time"),
                "processing_time": (datetime.now(timezone.utc) - start_ts).total_seconds(),
                "end_time": _iso_now(),
            },
            classification_results=classification_result,
            predictions=predictions,
        )

        total_duration = (datetime.now(timezone.utc) - start_ts).total_seconds()

        self._update_run(
            run_id,
            status="completed",
            progress=100,
            current_step="completed",
            current_message="Classification and reporting completed",
            step_name="report_generation",
            step_status="completed",
            step_message="HTML report generated",
            step_results={
                "report_file": report_file,
                "report_format": "html",
                "report_title": "eDNA Taxonomic Classification Report",
            },
            success=True,
            finished=True,
            processing_time=total_duration,
        )

        with self.lock:
            return self.runs[run_id]

    def start_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        requested_id = payload.get("sampleId") or f"sample-{uuid.uuid4().hex[:8]}"
        run_id = self._ensure_unique_run_id(requested_id)
        payload = dict(payload)
        payload["sampleId"] = run_id

        run = self._new_run_record(run_id, payload)
        with self.lock:
            self.runs[run_id] = run
            self._persist_run(run)

        future = self.executor.submit(self._run_task, run_id, payload)
        with self.lock:
            self.futures[run_id] = future

        return run

    def _run_task(self, run_id: str, payload: Dict[str, Any]) -> None:
        try:
            self._execute_embedding_run(run_id, payload)
            logger.info("Run %s completed", run_id)
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            self._update_run(
                run_id,
                status="failed",
                progress=100,
                current_step="failed",
                current_message=str(exc),
                step_status="failed",
                step_message=str(exc),
                error=str(exc),
                success=False,
                finished=True,
            )
        finally:
            with self.lock:
                self.futures.pop(run_id, None)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.runs.get(run_id)

    def list_recent_runs(self, limit: int = 25) -> List[Dict[str, Any]]:
        with self.lock:
            return sorted(
                self.runs.values(),
                key=lambda item: item.get("start_time", ""),
                reverse=True,
            )[:limit]

    def get_latest_active_run(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            active_runs = [
                run
                for run in self.runs.values()
                if str(run.get("status", "")).lower() in {"queued", "running", "pending"}
            ]
            if not active_runs:
                return None
            return sorted(active_runs, key=lambda item: item.get("start_time", ""), reverse=True)[0]

    def dashboard_snapshot(self) -> Dict[str, Any]:
        with self.lock:
            runs = list(self.runs.values())

        total_runs = len(runs)
        completed = [run for run in runs if _normalize_run_status(run.get("status"), run.get("success", False)) == "completed"]
        success_count = sum(1 for run in completed if run.get("success"))
        durations = [run.get("processing_time", 0) or 0 for run in completed if run.get("processing_time")]

        return {
            "totalRuns": total_runs,
            "successRate": (success_count / total_runs) if total_runs else 0.0,
            "avgDuration": int(sum(durations) / len(durations)) if durations else 0,
            "activeJobs": sum(1 for run in runs if run.get("status") == "running"),
            "queueDepth": sum(1 for run in runs if run.get("status") == "queued"),
            "lastRunAt": max((run.get("end_time") for run in completed if run.get("end_time")), default=None),
        }

    def start_batch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        batch_id = payload.get("batchId") or f"batch-{uuid.uuid4().hex[:8]}"
        runs_payload = payload.get("runs") or []

        batch = {
            "batch_id": batch_id,
            "total_samples": len(runs_payload),
            "successful_samples": 0,
            "failed_samples": 0,
            "start_time": _iso_now(),
            "end_time": None,
            "total_processing_time": None,
            "status": "queued",
            "summary_report": None,
            "sample_results": {},
            "error": None,
        }

        with self.lock:
            self.batches[batch_id] = batch
            self._persist_batch(batch)

        future = self.executor.submit(self._batch_task, batch_id, payload)
        with self.lock:
            self.batch_futures[batch_id] = future

        return batch

    def _batch_task(self, batch_id: str, payload: Dict[str, Any]) -> None:
        start_ts = datetime.now(timezone.utc)
        try:
            with self.lock:
                batch = self.batches[batch_id]
                batch["status"] = "running"
                batch["start_time"] = _iso_now()
                self._persist_batch(batch)

            runs_payload = payload.get("runs") or []
            for index, run_payload in enumerate(runs_payload, start=1):
                requested = run_payload.get("sampleId") or f"sample-{index}"
                run_id = self._ensure_unique_run_id(str(requested))
                run_payload = dict(run_payload)
                run_payload["sampleId"] = run_id

                run_record = self._new_run_record(run_id, run_payload)
                with self.lock:
                    self.runs[run_id] = run_record
                    self._persist_run(run_record)

                try:
                    final_run = self._execute_embedding_run(run_id, run_payload)
                except Exception as exc:
                    logger.exception("Batch %s run %s failed", batch_id, run_id)
                    self._update_run(
                        run_id,
                        status="failed",
                        progress=100,
                        current_step="failed",
                        current_message=str(exc),
                        step_status="failed",
                        step_message=str(exc),
                        error=str(exc),
                        success=False,
                        finished=True,
                    )
                    with self.lock:
                        final_run = self.runs[run_id]

                with self.lock:
                    batch = self.batches[batch_id]
                    batch["sample_results"][run_id] = final_run
                    if final_run.get("success"):
                        batch["successful_samples"] += 1
                    else:
                        batch["failed_samples"] += 1
                    self._persist_batch(batch)

            total_duration = (datetime.now(timezone.utc) - start_ts).total_seconds()
            with self.lock:
                batch = self.batches[batch_id]
                batch["status"] = "completed" if batch["failed_samples"] == 0 else "failed"
                batch["end_time"] = _iso_now()
                batch["total_processing_time"] = total_duration
                batch["summary_report"] = {
                    "success_rate": (
                        batch["successful_samples"] / batch["total_samples"]
                        if batch["total_samples"]
                        else 0.0
                    ),
                    "average_processing_time": (
                        total_duration / batch["total_samples"]
                        if batch["total_samples"]
                        else 0.0
                    ),
                }
                self._persist_batch(batch)
        except Exception as exc:
            logger.exception("Batch %s failed", batch_id)
            with self.lock:
                batch = self.batches[batch_id]
                batch["status"] = "failed"
                batch["error"] = str(exc)
                batch["end_time"] = _iso_now()
                self._persist_batch(batch)
        finally:
            with self.lock:
                self.batch_futures.pop(batch_id, None)

    def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.batches.get(batch_id)


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    manager = EmbeddingRunManager()

    def _resolve_requested_file(path_value: str) -> Path:
        if not path_value:
            raise ValueError("missing-path")

        requested_path = Path(path_value)
        if not requested_path.is_absolute():
            requested_path = (Path.cwd() / requested_path).resolve()
        else:
            requested_path = requested_path.resolve()

        for root in ALLOWED_FILE_ROOTS:
            try:
                requested_path.relative_to(root)
                break
            except ValueError:
                continue
        else:
            raise ValueError("path-not-allowed")

        if not requested_path.exists() or not requested_path.is_file():
            raise FileNotFoundError(str(requested_path))

        return requested_path

    def _read_logs(limit: int = 200) -> List[Dict[str, Any]]:
        log_path = LOG_DIR / "api.log"
        if not log_path.exists():
            return []

        with open(log_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()

        entries: List[Dict[str, Any]] = []
        for raw_line in lines[-limit:]:
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split(" - ", 2)
            if len(parts) != 3:
                entries.append({"timestamp": line, "level": "INFO", "message": line})
                continue
            timestamp, level, message = parts
            entries.append({"timestamp": timestamp, "level": level, "message": message})
        return entries

    @app.get("/api/health")
    def health() -> Any:
        return jsonify({"status": "ok", "timestamp": _iso_now()})

    @app.post("/api/auth/login")
    def login() -> Any:
        # Frontend expects a JWT-like login response; token is accepted as opaque.
        return jsonify({"access_token": "dev-token"}), 200

    @app.post("/api/uploads")
    def upload_fasta() -> Any:
        if "file" not in request.files:
            return jsonify({"error": "missing-file"}), 400

        uploaded = request.files["file"]
        if uploaded.filename == "":
            return jsonify({"error": "empty-filename"}), 400

        filename = secure_filename(uploaded.filename)
        if not filename:
            return jsonify({"error": "invalid-filename"}), 400

        if not _is_allowed_upload(filename):
            return jsonify({"error": "unsupported-extension", "message": "Upload FASTA files only"}), 400

        stored_name = f"{uuid.uuid4().hex}_{filename}"
        save_path = UPLOAD_DIR / stored_name
        uploaded.save(save_path)

        logger.info("Uploaded FASTA file %s to %s", filename, save_path)
        payload: Dict[str, Any] = {
            "file_name": filename,
            "stored_name": stored_name,
            "file_path": str(save_path.resolve()),
        }
        try:
            payload["relative_path"] = str(save_path.relative_to(Path.cwd()))
        except ValueError:
            pass

        return jsonify(payload), 201

    @app.get("/api/dashboard")
    def dashboard() -> Any:
        return jsonify(manager.dashboard_snapshot())

    @app.get("/api/runs/recent")
    def recent_runs() -> Any:
        return jsonify(manager.list_recent_runs())

    @app.get("/api/runs/active")
    def active_run() -> Any:
        run = manager.get_latest_active_run()
        if not run:
            return jsonify({"message": "No active run"}), 404
        return jsonify(run)

    @app.get("/api/runs/<run_id>")
    def run_detail(run_id: str) -> Any:
        run = manager.get_run(run_id)
        if not run:
            return jsonify({"message": "Run not found"}), 404
        return jsonify(run)

    @app.post("/api/runs")
    def trigger_run() -> Any:
        payload = request.get_json(silent=True) or {}
        try:
            run = manager.start_run(payload)
            logger.info("Queued run %s", run.get("sample_id"))
            return jsonify(run), 202
        except Exception as exc:
            logger.exception("Failed to queue run")
            return jsonify({"message": str(exc)}), 400

    @app.post("/api/runs/batch")
    def trigger_batch() -> Any:
        payload = request.get_json(silent=True) or {}
        try:
            batch = manager.start_batch(payload)
            logger.info("Queued batch %s", batch.get("batch_id"))
            return jsonify(batch), 202
        except Exception as exc:
            logger.exception("Failed to queue batch")
            return jsonify({"message": str(exc)}), 400

    @app.get("/api/runs/batch/<batch_id>")
    def batch_detail(batch_id: str) -> Any:
        batch = manager.get_batch(batch_id)
        if not batch:
            return jsonify({"message": "Batch not found"}), 404
        return jsonify(batch)

    @app.get("/api/logs")
    def api_logs() -> Any:
        return jsonify({
            "entries": _read_logs(),
            "download_path": str((LOG_DIR / "api.log").resolve()),
        })

    @app.get("/api/files")
    def download_file() -> Any:
        file_path = request.args.get("path")
        mode = request.args.get("mode", "attachment")
        download_name = request.args.get("name")

        try:
            resolved = _resolve_requested_file(file_path or "")
        except FileNotFoundError:
            return jsonify({"message": "file-not-found"}), 404
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400

        as_attachment = mode != "inline"
        return send_file(resolved, as_attachment=as_attachment, download_name=download_name or resolved.name)

    return app


if __name__ == "__main__":  # pragma: no cover
    application = create_app()
    application.run(host="0.0.0.0", port=8000)
