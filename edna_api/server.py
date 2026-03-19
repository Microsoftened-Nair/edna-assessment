import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from edna_pipeline.database_manager import DatabaseManager
from edna_pipeline.pipeline import DeepSeaEDNAPipeline
from edna_api.database import init_db, User

BASE_DATA_DIR = Path("data/api")
RUNS_DIR = BASE_DATA_DIR / "runs"
BATCH_DIR = BASE_DATA_DIR / "batches"
LOG_DIR = BASE_DATA_DIR / "logs"
UPLOAD_DIR = BASE_DATA_DIR / "uploads"
for directory in (RUNS_DIR, BATCH_DIR, LOG_DIR, UPLOAD_DIR):
    directory.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("edna_api")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(LOG_DIR / "api.log")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

DEFAULT_DB_DIR = os.environ.get("EDNA_DB_DIR", "databases")

ALLOWED_FILE_ROOTS = [
    (Path.cwd() / "results").resolve(),
    BASE_DATA_DIR.resolve(),
    (Path.cwd() / DEFAULT_DB_DIR).resolve(),
]

ALLOWED_FASTQ_SUFFIXES = {".fastq", ".fq", ".fastq.gz", ".fq.gz"}


def _iso_now() -> str:
    return datetime.utcnow().isoformat()


def _to_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _is_allowed_upload(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in ALLOWED_FASTQ_SUFFIXES)


class RunManager:
    def __init__(self, db_dir: str = "demo_databases", max_workers: int = 2):
        self.db_dir = db_dir
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures: Dict[str, Any] = {}
        self.runs: Dict[str, Dict[str, Any]] = {}
        self._load_runs()

    # Persistence helpers
    def _run_path(self, run_id: str) -> Path:
        return RUNS_DIR / f"{run_id}.json"

    def _load_runs(self) -> None:
        for path in RUNS_DIR.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    if isinstance(data, dict) and data.get("sample_id"):
                        self.runs[data["sample_id"]] = data
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to load run file %s: %s", path, exc)
        self._prune_missing_runs()

    def _persist_run(self, run: Dict[str, Any]) -> None:
        path = self._run_path(run["sample_id"])
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(run, handle, indent=2)

    def _prune_missing_runs(self) -> None:
        """Drop runs whose output directories have been removed from disk."""
        removed: List[str] = []
        for run_id, run in list(self.runs.items()):
            status = (run.get("status") or "").lower()
            if status in {"queued", "running"}:
                continue
            output_dir = run.get("output_dir")
            if not output_dir:
                continue
            candidate = Path(output_dir)
            if not candidate.is_absolute():
                candidate = (Path.cwd() / candidate).resolve()
            else:
                candidate = candidate.resolve()
            if candidate.exists():
                continue
            self.runs.pop(run_id, None)
            removed.append(run_id)
            try:
                self._run_path(run_id).unlink()
            except FileNotFoundError:
                pass
        if removed:
            logger.info("Pruned runs with missing outputs: %s", ", ".join(removed))

    # Public API
    def list_recent(self, limit: int = 25) -> List[Dict[str, Any]]:
        with self.lock:
            self._prune_missing_runs()
            runs = sorted(self.runs.values(), key=lambda item: item.get("start_time", ""), reverse=True)
            return runs[:limit]

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.runs.get(run_id)

    def dashboard_snapshot(self) -> Dict[str, Any]:
        with self.lock:
            self._prune_missing_runs()
            runs = list(self.runs.values())

        total_runs = len(runs)
        completed = [run for run in runs if run.get("status") == "completed"]
        success_count = sum(1 for run in completed if run.get("success"))
        durations = [run.get("processing_time", 0) or 0 for run in completed if run.get("processing_time")]
        avg_duration = int(sum(durations) / len(durations)) if durations else 0
        last_run_at = max((run.get("end_time") for run in completed if run.get("end_time")), default=None)
        active_jobs = sum(1 for run in runs if run.get("status") == "running")
        queue_depth = sum(1 for run in runs if run.get("status") == "queued")

        return {
            "totalRuns": total_runs,
            "successRate": (success_count / total_runs) if total_runs else 0.0,
            "avgDuration": avg_duration,
            "activeJobs": active_jobs,
            "queueDepth": queue_depth,
            "lastRunAt": last_run_at,
        }

    def record_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        run = self._normalize_result(result)
        with self.lock:
            self.runs[run["sample_id"]] = run
            self._persist_run(run)
        return run

    def start_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        requested_id = payload.get("sampleId") or f"sample-{uuid.uuid4().hex[:8]}"
        run_id = self._ensure_unique_run_id(requested_id)
        payload["sampleId"] = run_id

        run_record = {
            "sample_id": run_id,
            "input_type": payload.get("inputType", "single"),
            "input_files": payload.get("files", []),
            "output_dir": payload.get("configOverrides", {}).get("output.dir", "results"),
            "start_time": _iso_now(),
            "end_time": None,
            "processing_time": None,
            "success": False,
            "error": None,
            "status": "queued",
            "pipeline_steps": [],
        }

        with self.lock:
            self.runs[run_id] = run_record
            self._persist_run(run_record)

        future = self.executor.submit(self._execute_run, run_id, payload)
        with self.lock:
            self.futures[run_id] = future
        return run_record

    # Internal
    def _ensure_unique_run_id(self, base_id: str) -> str:
        with self.lock:
            if base_id not in self.runs:
                return base_id
            suffix = 1
            while f"{base_id}-{suffix}" in self.runs:
                suffix += 1
            return f"{base_id}-{suffix}"

    def _execute_run(self, run_id: str, payload: Dict[str, Any]) -> None:
        with self.lock:
            run = self.runs[run_id]
            run["status"] = "running"
            run["start_time"] = _iso_now()
            self._persist_run(run)

        try:
            pipeline = DeepSeaEDNAPipeline(db_dir=self.db_dir)
            input_type = payload.get("inputType", "single")
            files = payload.get("files", [])
            if input_type == "paired" and len(files) >= 2:
                input_files: Any = (files[0], files[1])
            else:
                input_files = files[0] if files else ""

            output_dir = payload.get("configOverrides", {}).get("output.dir") or "results"
            result = pipeline.process_sample(
                input_files=input_files,
                sample_id=payload["sampleId"],
                output_dir=output_dir,
            )
            run_data = self._normalize_result(result)
        except Exception as exc:  # pragma: no cover
            logger.exception("Run %s failed", run_id)
            with self.lock:
                run = self.runs[run_id]
                run["status"] = "failed"
                run["success"] = False
                run["error"] = str(exc)
                run["end_time"] = _iso_now()
                self._persist_run(run)
            return
        finally:
            with self.lock:
                self.futures.pop(run_id, None)

        with self.lock:
            self.runs[run_id] = run_data
            self._persist_run(run_data)

    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        run = {
            "sample_id": result.get("sample_id"),
            "input_type": result.get("input_type"),
            "input_files": _to_list(result.get("input_files")),
            "output_dir": result.get("output_dir"),
            "start_time": result.get("start_time"),
            "end_time": result.get("end_time"),
            "processing_time": result.get("processing_time"),
            "success": result.get("success", False),
            "error": result.get("error"),
            "status": result.get("status")
            or ("completed" if result.get("success") else "failed"),
            "pipeline_steps": result.get("pipeline_steps", []),
        }
        if not run["start_time"]:
            run["start_time"] = _iso_now()
        if not run["end_time"] and run["status"] != "completed":
            run["end_time"] = None
        return run


class BatchManager:
    def __init__(self, run_manager: RunManager, db_dir: str = "demo_databases"):
        self.run_manager = run_manager
        self.db_dir = db_dir
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.batches: Dict[str, Dict[str, Any]] = {}
        self.futures: Dict[str, Any] = {}
        self._load_batches()

    def _batch_path(self, batch_id: str) -> Path:
        return BATCH_DIR / f"{batch_id}.json"

    def _load_batches(self) -> None:
        for path in BATCH_DIR.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    if isinstance(data, dict) and data.get("batch_id"):
                        self.batches[data["batch_id"]] = data
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to load batch file %s: %s", path, exc)

    def _persist_batch(self, batch: Dict[str, Any]) -> None:
        with open(self._batch_path(batch["batch_id"]), "w", encoding="utf-8") as handle:
            json.dump(batch, handle, indent=2)

    def get(self, batch_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.batches.get(batch_id)

    def start_batch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        batch_id = payload.get("batchId") or f"batch-{uuid.uuid4().hex[:8]}"
        batch_record = {
            "batch_id": batch_id,
            "total_samples": len(payload.get("runs", [])),
            "successful_samples": 0,
            "failed_samples": 0,
            "start_time": _iso_now(),
            "end_time": None,
            "total_processing_time": None,
            "status": "queued",
            "summary_report": None,
            "sample_results": {},
        }
        with self.lock:
            self.batches[batch_id] = batch_record
            self._persist_batch(batch_record)

        future = self.executor.submit(self._execute_batch, batch_id, payload)
        with self.lock:
            self.futures[batch_id] = future
        return batch_record

    def _execute_batch(self, batch_id: str, payload: Dict[str, Any]) -> None:
        with self.lock:
            batch = self.batches[batch_id]
            batch["status"] = "running"
            batch["start_time"] = _iso_now()
            self._persist_batch(batch)

        try:
            pipeline = DeepSeaEDNAPipeline(db_dir=self.db_dir)
            sample_list = []
            for run_payload in payload.get("runs", []):
                sample_id = run_payload.get("sampleId") or f"sample-{uuid.uuid4().hex[:8]}"
                files = run_payload.get("files", [])
                if run_payload.get("inputType") == "paired" and len(files) >= 2:
                    sample_files: Any = (files[0], files[1])
                else:
                    sample_files = files[0] if files else ""
                sample_list.append({
                    "files": sample_files,
                    "sample_id": sample_id,
                })

            output_dir = payload.get("outputDir") or "batch_results"
            result = pipeline.process_batch(sample_list, output_dir=output_dir)
            batch_data = self._normalize_batch_result(result)
        except Exception as exc:  # pragma: no cover
            logger.exception("Batch %s failed", batch_id)
            with self.lock:
                batch = self.batches[batch_id]
                batch["status"] = "failed"
                batch["failed_samples"] = batch.get("total_samples", 0)
                batch["error"] = str(exc)
                batch["end_time"] = _iso_now()
                self._persist_batch(batch)
            return
        finally:
            with self.lock:
                self.futures.pop(batch_id, None)

        for sample_id, sample_result in batch_data.get("sample_results", {}).items():
            self.run_manager.record_result(sample_result)

        with self.lock:
            self.batches[batch_id] = batch_data
            self._persist_batch(batch_data)

    def _normalize_batch_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        sample_results = {}
        for sample_id, sample_data in result.get("sample_results", {}).items():
            normalized = self.run_manager._normalize_result(sample_data)
            sample_results[sample_id] = normalized

        batch = {
            "batch_id": result.get("batch_id") or f"batch-{uuid.uuid4().hex[:8]}",
            "total_samples": result.get("total_samples", len(sample_results)),
            "successful_samples": result.get("successful_samples", 0),
            "failed_samples": result.get("failed_samples", 0),
            "start_time": result.get("start_time"),
            "end_time": result.get("end_time"),
            "total_processing_time": result.get("total_processing_time"),
            "status": result.get("status")
            or ("completed" if result.get("failed_samples", 0) == 0 else "failed"),
            "summary_report": result.get("summary_report"),
            "sample_results": sample_results,
            "error": result.get("error"),
        }
        if not batch["start_time"]:
            batch["start_time"] = _iso_now()
        if not batch["end_time"]:
            batch["end_time"] = _iso_now()
        return batch


class DatabaseTaskManager:
    def __init__(self, db_dir: str = "demo_databases"):
        self.db_manager = DatabaseManager(db_dir=db_dir)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.active_tasks: Dict[str, Any] = {}

    def list_databases(self) -> List[Dict[str, Any]]:
        info = self.db_manager.get_database_info()
        databases: List[Dict[str, Any]] = []
        for name, meta in info.items():
            status_payload = {
                "downloaded": meta.get("downloaded", 0),
                "total": meta.get("total", 0),
                "status": meta.get("status", "not_downloaded"),
                "last_updated": meta.get("last_updated"),
            }
            databases.append({
                "name": name,
                "description": meta.get("description", ""),
                "use_case": meta.get("use_case", ""),
                "priority": meta.get("priority", "medium"),
                "status": status_payload,
            })
        return databases

    def start_download(self, name: str) -> Dict[str, Any]:
        with self.lock:
            if name in self.active_tasks:
                raise ValueError("download-already-running")
            future = self.executor.submit(self._run_download, name)
            self.active_tasks[name] = future
        return {"name": name, "status": {"status": "running"}}

    def cancel_download(self, name: str) -> None:
        with self.lock:
            future = self.active_tasks.get(name)
            if future is None:
                raise ValueError("no-active-download")
            if future.done():
                self.active_tasks.pop(name, None)
                return
            raise ValueError("cannot-cancel-in-progress")

    def _run_download(self, name: str) -> None:
        try:
            self.db_manager.download_database(name)
        finally:
            with self.lock:
                self.active_tasks.pop(name, None)


def create_app(db_dir: str | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app)
    
    # Configure JWT
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-super-secret-key-change-in-prod")
    jwt = JWTManager(app)
    
    # Configure DB
    init_db(app)

    database_root = db_dir or DEFAULT_DB_DIR

    run_manager = RunManager(db_dir=database_root)
    batch_manager = BatchManager(run_manager, db_dir=database_root)
    database_tasks = DatabaseTaskManager(db_dir=database_root)

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

        try:
            with open(log_path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            return []

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
            entries.append({
                "timestamp": timestamp,
                "level": level,
                "message": message,
            })
        return entries

    @app.get("/api/health")
    def health() -> Any:
        return jsonify({"status": "ok", "timestamp": _iso_now()})

    @app.get("/api/dashboard")
    def dashboard() -> Any:
        return jsonify(run_manager.dashboard_snapshot())

    @app.post("/api/uploads")
    def upload_fastq() -> Any:
        if "file" not in request.files:
            return jsonify({"error": "missing-file"}), 400

        uploaded = request.files["file"]
        if uploaded.filename == "":
            return jsonify({"error": "empty-filename"}), 400

        filename = secure_filename(uploaded.filename)
        if not filename:
            return jsonify({"error": "invalid-filename"}), 400

        if not _is_allowed_upload(filename):
            return jsonify({"error": "unsupported-extension"}), 400

        stored_name = f"{uuid.uuid4().hex}_{filename}"
        save_path = UPLOAD_DIR / stored_name
        uploaded.save(save_path)

        payload: Dict[str, Any] = {
            "file_name": filename,
            "stored_name": stored_name,
            "file_path": str(save_path.resolve()),
        }

        try:
            payload["relative_path"] = str(save_path.relative_to(Path.cwd()))
        except ValueError:
            # Path is not relative to current working directory; ignore
            pass

        logger.info("Uploaded FASTQ file %s to %s", filename, save_path)
        return jsonify(payload), 201

    @app.post("/api/auth/login")
    def login():
        data = request.get_json(silent=True) or {}
        username = data.get("username")
        password = data.get("password")
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            access_token = create_access_token(identity=username)
            return jsonify(access_token=access_token), 200
        return jsonify({"msg": "Bad username or password"}), 401

    @app.get("/api/runs/recent")
    @jwt_required()
    def recent_runs() -> Any:
        runs = run_manager.list_recent()
        logger.info("Recent runs requested: count=%s", len(runs))
        return jsonify(runs)

    @app.get("/api/runs/<run_id>")
    @jwt_required()
    def run_detail(run_id: str) -> Any:
        run = run_manager.get(run_id)
        if not run:
            return jsonify({"message": "Run not found"}), 404
        return jsonify(run)

    @app.post("/api/runs")
    @jwt_required()
    def trigger_run() -> Any:
        payload = request.get_json(silent=True) or {}
        try:
            run = run_manager.start_run(payload)
        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to queue run")
            return jsonify({"message": str(exc)}), 400
        return jsonify(run), 202

    @app.post("/api/runs/batch")
    @jwt_required()
    def trigger_batch() -> Any:
        payload = request.get_json(silent=True) or {}
        try:
            batch = batch_manager.start_batch(payload)
        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to queue batch")
            return jsonify({"message": str(exc)}), 400
        return jsonify(batch), 202

    @app.get("/api/runs/batch/<batch_id>")
    @jwt_required()
    def batch_detail(batch_id: str) -> Any:
        batch = batch_manager.get(batch_id)
        if not batch:
            return jsonify({"message": "Batch not found"}), 404
        return jsonify(batch)

    @app.get("/api/databases")
    @jwt_required()
    def list_databases() -> Any:
        return jsonify(database_tasks.list_databases())

    @app.post("/api/databases/<name>/download")
    @jwt_required()
    def download_database(name: str) -> Any:
        try:
            database_tasks.start_download(name)
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        return jsonify(next((db for db in database_tasks.list_databases() if db["name"] == name), {"name": name}))

    @app.post("/api/databases/<name>/cancel")
    @jwt_required()
    def cancel_database(name: str) -> Any:
        try:
            database_tasks.cancel_download(name)
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        return jsonify({"name": name, "status": "cancelled"})

    @app.get("/api/logs")
    def api_logs() -> Any:
        entries = _read_logs()
        return jsonify({
            "entries": entries,
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
