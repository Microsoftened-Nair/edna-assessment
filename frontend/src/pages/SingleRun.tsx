import { ChangeEvent, DragEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { FiPlay, FiUploadCloud } from "react-icons/fi";
import clsx from "clsx";
import api from "../services/api";
import type { PipelineRun } from "../types/pipeline";

interface RunFormState {
  sampleId: string;
  inputType: "single" | "paired";
  forwardPath: string;
  reversePath: string;
  outputDir: string;
}

const defaultState: RunFormState = {
  sampleId: "abyssal_sample",
  inputType: "single",
  forwardPath: "",
  reversePath: "",
  outputDir: "results"
};

const allowedFastaExtensions = [".fasta", ".fa", ".fasta.gz", ".fa.gz"] as const;
type UploadSlot = "forward" | "reverse";

interface UploadSlotState {
  uploading: boolean;
  name?: string;
  error?: string;
  dragging?: boolean;
}

interface AppSettings {
  defaultOutputDir: string;
  defaultInputType: "single" | "paired";
  modelName: string;
  maxLength: number;
  batchSize: number;
  device: "auto" | "cpu" | "cuda";
  runPollIntervalMs: number;
}

const DEFAULT_APP_SETTINGS: AppSettings = {
  defaultOutputDir: "results",
  defaultInputType: "single",
  modelName: "zhihan1996/DNABERT-2-117M",
  maxLength: 256,
  batchSize: 16,
  device: "auto",
  runPollIntervalMs: 2000
};

const ACTIVE_SINGLE_RUN_STORAGE_KEY = "edna_active_single_run_id";
const SETTINGS_STORAGE_KEY = "edna-app-settings";

const getRunState = (run: PipelineRun): string =>
  (run.status ?? (run.success ? "completed" : "failed")).toLowerCase();

const isRunActive = (run: PipelineRun): boolean => {
  const state = getRunState(run);
  return state === "queued" || state === "running" || state === "pending";
};

const getStoredActiveRunId = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(ACTIVE_SINGLE_RUN_STORAGE_KEY);
};

const storeActiveRunId = (runId: string): void => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(ACTIVE_SINGLE_RUN_STORAGE_KEY, runId);
};

const clearStoredActiveRunId = (): void => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(ACTIVE_SINGLE_RUN_STORAGE_KEY);
};

const loadAppSettings = (): AppSettings => {
  if (typeof window === "undefined") {
    return DEFAULT_APP_SETTINGS;
  }

  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) {
      return DEFAULT_APP_SETTINGS;
    }
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    return {
      ...DEFAULT_APP_SETTINGS,
      ...parsed,
      maxLength: Number(parsed.maxLength ?? DEFAULT_APP_SETTINGS.maxLength),
      batchSize: Number(parsed.batchSize ?? DEFAULT_APP_SETTINGS.batchSize),
      runPollIntervalMs: Number(parsed.runPollIntervalMs ?? DEFAULT_APP_SETTINGS.runPollIntervalMs)
    };
  } catch {
    return DEFAULT_APP_SETTINGS;
  }
};

const SingleRun = () => {
  const [formState, setFormState] = useState<RunFormState>(defaultState);
  const [appSettings, setAppSettings] = useState<AppSettings>(DEFAULT_APP_SETTINGS);
  const [submitting, setSubmitting] = useState(false);
  const [latestRun, setLatestRun] = useState<PipelineRun | null>(null);
  const [backendHasActiveJobs, setBackendHasActiveJobs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadState, setUploadState] = useState<{ forward: UploadSlotState; reverse: UploadSlotState }>({
    forward: { uploading: false },
    reverse: { uploading: false }
  });
  const forwardFileInputRef = useRef<HTMLInputElement | null>(null);
  const reverseFileInputRef = useRef<HTMLInputElement | null>(null);
  const isMountedRef = useRef(true);
  const pollingRunIdRef = useRef<string | null>(null);

  const pollRunStatus = useCallback(async (runId: string) => {
    const pollIntervalMs = Math.max(500, appSettings.runPollIntervalMs || 2000);
    const maxAttempts = 86400; // Increased to prevent premature timeouts during longer runs
    let attempts = 0;

    try {
      const initial = await api.fetchRunDetails(runId);
      if (!isMountedRef.current || pollingRunIdRef.current !== runId) {
        return;
      }
      setLatestRun(initial);
      const initialState = getRunState(initial);
      if (initialState === "completed" || initialState === "failed") {
        pollingRunIdRef.current = null;
        clearStoredActiveRunId();
        window.dispatchEvent(new CustomEvent("app:refresh-data"));
        return;
      }
    } catch {
      // Continue with interval polling.
    }

    while (isMountedRef.current && pollingRunIdRef.current === runId && attempts < maxAttempts) {
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      if (!isMountedRef.current || pollingRunIdRef.current !== runId) {
        return;
      }

      try {
        const refreshed = await api.fetchRunDetails(runId);
        if (!isMountedRef.current) {
          return;
        }
        setLatestRun(refreshed);
        const state = getRunState(refreshed);
        if (state === "completed" || state === "failed") {
          pollingRunIdRef.current = null;
          clearStoredActiveRunId();
          window.dispatchEvent(new CustomEvent("app:refresh-data"));
          return;
        }
      } catch (pollError) {
        if (!isMountedRef.current) {
          return;
        }
        // Don't log to state unconditionally to avoid cluttering, and DO NOT return/halt.
        // We want to continue interval polling so it naturally recovers from a blip.
      }

      attempts += 1;
    }

    if (isMountedRef.current && attempts >= maxAttempts) {
      setError((prev) => prev ?? "Run is still in progress. Check the Results page for the latest status.");
    }
  }, [appSettings.runPollIntervalMs]);

  const latestRunState = latestRun ? getRunState(latestRun) : "";
  const hasActiveRun = latestRun != null && (latestRunState === "queued" || latestRunState === "running" || latestRunState === "pending");
  const shouldLockSingleRun = hasActiveRun || backendHasActiveJobs;
  const latestRunMessage = latestRun?.current_message
    ?? (typeof latestRun?.pipeline_steps?.[0]?.results?.message === "string"
      ? latestRun.pipeline_steps[0].results.message
      : null)
    ?? "Processing...";

  useEffect(() => () => {
    isMountedRef.current = false;
    pollingRunIdRef.current = null;
  }, []);

  useEffect(() => {
    const loaded = loadAppSettings();
    setAppSettings(loaded);
    setFormState((state) => ({
      ...state,
      inputType: loaded.defaultInputType,
      reversePath: loaded.defaultInputType === "single" ? "" : state.reversePath,
      outputDir: loaded.defaultOutputDir || state.outputDir
    }));
  }, []);

  useEffect(() => {
    const bootstrapLatestRun = async () => {
      const storedRunId = getStoredActiveRunId();
      if (storedRunId) {
        try {
          const storedRun = await api.fetchRunDetails(storedRunId);
          if (!isMountedRef.current) {
            return;
          }
          setLatestRun(storedRun);
          if (isRunActive(storedRun)) {
            pollingRunIdRef.current = storedRun.sample_id;
            void pollRunStatus(storedRun.sample_id);
            return;
          }
          clearStoredActiveRunId();
        } catch {
          clearStoredActiveRunId();
        }
      }

      try {
        const runs = await api.fetchRecentRuns();
        if (!isMountedRef.current || !runs.length) {
          return;
        }
        const active = runs.find((run) => isRunActive(run));
        const selected = active ?? runs[0];
        setLatestRun(selected);
        if (active) {
          storeActiveRunId(active.sample_id);
          pollingRunIdRef.current = active.sample_id;
          void pollRunStatus(active.sample_id);
        } else {
          clearStoredActiveRunId();
        }
      } catch {
        // Non-blocking bootstrap; regular interactions still work.
      }
    };

    void bootstrapLatestRun();
  }, [pollRunStatus]);

  useEffect(() => {
    let cancelled = false;

    const refreshActiveJobs = async () => {
      try {
        const snapshot = await api.fetchDashboardSnapshot();
        if (!cancelled) {
          const hasActiveJobsNow = (snapshot.activeJobs ?? 0) > 0;
          setBackendHasActiveJobs(hasActiveJobsNow);

          if (hasActiveJobsNow) {
            try {
              const activeRun = await api.fetchActiveRun();
              if (!cancelled && activeRun) {
                setLatestRun(activeRun);
                storeActiveRunId(activeRun.sample_id);
                if (isRunActive(activeRun) && pollingRunIdRef.current !== activeRun.sample_id) {
                  pollingRunIdRef.current = activeRun.sample_id;
                  void pollRunStatus(activeRun.sample_id);
                }
              }
            } catch {
              // Keep lock state from dashboard snapshot even if active-run detail fetch fails.
            }
          }
        }
      } catch {
        if (!cancelled) {
          setBackendHasActiveJobs(false);
        }
      }
    };

    void refreshActiveJobs();
    const timer = window.setInterval(() => {
      void refreshActiveJobs();
    }, Math.max(500, appSettings.runPollIntervalMs || 2000));

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [appSettings.runPollIntervalMs, pollRunStatus]);

  useEffect(() => {
    const handleRefresh = async () => {
      const activeId = pollingRunIdRef.current || latestRun?.sample_id;
      if (activeId) {
        try {
          const run = await api.fetchRunDetails(activeId);
          if (isMountedRef.current) {
            setLatestRun(run);
            if (!isRunActive(run) && pollingRunIdRef.current === run.sample_id) {
              pollingRunIdRef.current = null;
              clearStoredActiveRunId();
            }
          }
        } catch {}
      }
    };
    window.addEventListener("app:refresh-data", handleRefresh);
    return () => window.removeEventListener("app:refresh-data", handleRefresh);
  }, [latestRun?.sample_id]);

  const isValidFasta = (filename: string) =>
    allowedFastaExtensions.some((extension) => filename.toLowerCase().endsWith(extension));

  const updateUploadSlot = (slot: UploadSlot, partial: Partial<UploadSlotState>) => {
    setUploadState((state) => ({
      ...state,
      [slot]: {
        ...state[slot],
        ...partial
      }
    }));
  };

  const getInputRef = (slot: UploadSlot) => (slot === "forward" ? forwardFileInputRef : reverseFileInputRef);

  const openFileDialog = (slot: UploadSlot) => {
    const ref = getInputRef(slot);
    ref.current?.click();
  };

  const handleFileUpload = async (file: File, slot: UploadSlot) => {
    if (!isValidFasta(file.name)) {
      updateUploadSlot(slot, {
        uploading: false,
        name: undefined,
        dragging: false,
        error: "Unsupported file type. Upload .fasta, .fa, or .gz versions of these."

      });
      return;
    }

    updateUploadSlot(slot, {
      uploading: true,
      name: file.name,
      error: undefined,
      dragging: false
    });

    try {
      const result = await api.uploadRunFile(file);
      const savedPath = result.relative_path ?? result.file_path;

      setFormState((state) =>
        slot === "forward"
          ? { ...state, forwardPath: savedPath }
          : { ...state, reversePath: savedPath }
      );

      updateUploadSlot(slot, {
        uploading: false,
        name: file.name,
        error: undefined,
        dragging: false
      });
    } catch (uploadError) {
      const message = uploadError instanceof Error ? uploadError.message : "Upload failed";
      updateUploadSlot(slot, {
        uploading: false,
        error: message,
        dragging: false
      });
    }
  };

  const handleFileSelection = async (event: ChangeEvent<HTMLInputElement>, slot: UploadSlot) => {
    const file = event.target.files?.[0];
    if (file) {
      await handleFileUpload(file, slot);
    }
    // Reset the input so the same file can be chosen again if needed
    event.target.value = "";
  };

  const handleDragState = (event: DragEvent<HTMLDivElement>, slot: UploadSlot, active: boolean) => {
    event.preventDefault();
    event.stopPropagation();
    updateUploadSlot(slot, { dragging: active });
  };

  const handleDrop = async (event: DragEvent<HTMLDivElement>, slot: UploadSlot) => {
    event.preventDefault();
    event.stopPropagation();
    updateUploadSlot(slot, { dragging: false });

    const file = event.dataTransfer.files?.[0];
    if (file) {
      await handleFileUpload(file, slot);
    }
  };

  const handleInputTypeChange = (value: RunFormState["inputType"]) => {
    setFormState((state) => ({
      ...state,
      inputType: value,
      reversePath: value === "paired" ? state.reversePath : ""
    }));

    if (value === "single") {
      setUploadState((state) => ({
        ...state,
        reverse: { uploading: false, name: undefined, error: undefined, dragging: false }
      }));
    }
  };

  const renderUploadSection = (slot: UploadSlot) => {
    const slotState = uploadState[slot];
    const currentPath = slot === "forward" ? formState.forwardPath : formState.reversePath;

    return (
      <div className="upload-dropzone-wrapper">
        <div
          className={clsx("upload-dropzone", {
            "upload-dropzone--drag": Boolean(slotState.dragging),
            "upload-dropzone--uploading": slotState.uploading
          })}
          onDragOver={(event) => event.preventDefault()}
          onDragEnter={(event) => handleDragState(event, slot, true)}
          onDragLeave={(event) => handleDragState(event, slot, false)}
          onDrop={(event) => handleDrop(event, slot)}
          onClick={() => openFileDialog(slot)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              openFileDialog(slot);
            }
          }}
          role="button"
          tabIndex={0}
        >
          <div className="upload-dropzone__icon">
            <FiUploadCloud />
          </div>
          <div className="upload-dropzone__content">
            <div className="upload-dropzone__title">
              {slotState.uploading ? "Uploading..." : "Drop FASTA or click to choose"}
            </div>
            <div className="upload-dropzone__subtitle">
              {slotState.name
                ? `Selected: ${slotState.name}`
                : "Accepted formats: .fasta, .fa, .gz"}
            </div>
            {currentPath ? (
              <div className="upload-dropzone__path">Saved to: {currentPath}</div>
            ) : (
              <div className="upload-dropzone__path upload-dropzone__path--placeholder">
                Server path will appear after upload
              </div>
            )}
          </div>
        </div>
        <input
          ref={slot === "forward" ? forwardFileInputRef : reverseFileInputRef}
          type="file"
          accept=".fasta,.fa,.fasta.gz,.fa.gz"
          style={{ display: "none" }}
          onChange={(event) => handleFileSelection(event, slot)}
        />
        {slotState.error ? (
          <div style={{ color: "#ff7b89", fontSize: "13px" }}>{slotState.error}</div>
        ) : null}
      </div>
    );
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (shouldLockSingleRun) {
      setError("A single run is already in progress. Start a new run after it completes.");
      return;
    }
    if (!formState.forwardPath || (formState.inputType === "paired" && !formState.reversePath)) {
      setError("Provide a server-accessible FASTA path for all required reads.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const configOverrides: Record<string, unknown> = {
        "output.dir": formState.outputDir || appSettings.defaultOutputDir,
        "model.name": appSettings.modelName,
        "max.length": Math.max(32, Number(appSettings.maxLength) || 256),
        "batch.size": Math.max(1, Number(appSettings.batchSize) || 16),
        "classification.model_bundle": "models/embedding_model_bundle.joblib"
      };
      if (appSettings.device !== "auto") {
        configOverrides.device = appSettings.device;
      }

      const payload = {
        sampleId: formState.sampleId,
        inputType: formState.inputType,
        files:
          formState.inputType === "paired"
            ? [formState.forwardPath, formState.reversePath]
            : [formState.forwardPath],
        configOverrides
      };
      const run = await api.triggerRun(payload);
      setLatestRun(run);
      storeActiveRunId(run.sample_id);
      pollingRunIdRef.current = run.sample_id;
      void pollRunStatus(run.sample_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page-grid" style={{ gap: "28px", maxWidth: "1100px" }}>
      {shouldLockSingleRun ? (
        <section className="card" style={{ display: "grid", gap: "20px" }}>
          <div className="section-title">
            <h3>Active single-run analysis</h3>
            <span>A run is currently in progress. New single runs are locked until completion.</span>
          </div>

          {latestRun ? (
            <div style={{ display: "grid", gap: "14px" }}>
              <div style={{ display: "flex", gap: "12px", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
                <div>
                  <div className="stat-card__label">Sample</div>
                  <div className="stat-card__value">{latestRun.sample_id}</div>
                </div>
                <span className="status-pill status-pill--pending" style={{ alignSelf: "flex-start" }}>
                  {latestRunState === "queued" ? "Queued" : latestRunState === "pending" ? "Pending" : "Running"}
                </span>
              </div>

              <div style={{ display: "grid", gap: "8px" }}>
                <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>{latestRunMessage}</div>
                {latestRun.current_step ? (
                  <div style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "capitalize" }}>
                    Step: {latestRun.current_step.replace(/_/g, " ")}
                  </div>
                ) : null}
                <div style={{ height: "8px", width: "100%", borderRadius: "999px", background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                  <div
                    style={{
                      height: "100%",
                      width: `${Math.max(0, Math.min(100, latestRun.progress ?? 0))}%`,
                      background: "linear-gradient(90deg, var(--accent), #43d29d)",
                      transition: "width 300ms ease"
                    }}
                  />
                </div>
                <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                  {Math.max(0, Math.min(100, latestRun.progress ?? 0)).toFixed(0)}% complete
                </div>
              </div>

              <div style={{ display: "grid", gap: "8px", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                <div className="form-control">
                  <label>Started</label>
                  <span>{latestRun.start_time ?? "--"}</span>
                </div>
                <div className="form-control">
                  <label>Output directory</label>
                  <span>{latestRun.output_dir}</span>
                </div>
              </div>

              <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                <Link to={`/results/${latestRun.sample_id}`} className="secondary-button">
                  View details
                </Link>
              </div>
            </div>
          ) : (
            <div style={{ display: "grid", gap: "10px" }}>
              <span className="status-pill status-pill--pending">Single Run Locked</span>
              <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                A backend run is currently active. Waiting for latest run telemetry to sync.
              </div>
            </div>
          )}
        </section>
      ) : (
        <section className="card" style={{ display: "grid", gap: "24px" }}>
          <div className="section-title">
            <h3>Launch single-sample analysis</h3>
            <span>Configure the ingest parameters and kick off the AI pipeline</span>
          </div>
          <form className="form-grid" onSubmit={handleSubmit}>
            <div className="form-control">
              <label htmlFor="sampleId">Sample identifier</label>
              <input
                id="sampleId"
                value={formState.sampleId}
                onChange={(event) => setFormState((state) => ({ ...state, sampleId: event.target.value }))}
                placeholder="e.g. abyssal_ridge_01"
                required
              />
            </div>

            <div className="form-control">
              <label htmlFor="inputType">Read format</label>
              <select
                id="inputType"
                value={formState.inputType}
                onChange={(event) => handleInputTypeChange(event.target.value as RunFormState["inputType"])}
              >
                <option value="single">Single-end FASTA</option>
                <option value="paired">Paired-end FASTA</option>
              </select>
            </div>

            <div className="form-control">
              <label htmlFor="forwardPath">
                {formState.inputType === "paired" ? "Forward reads (R1)" : "FASTA file"}
              </label>
              <input
                id="forwardPath"
                value={formState.forwardPath}
                onChange={(event) => {
                  const value = event.target.value;
                  setFormState((state) => ({ ...state, forwardPath: value }));
                  updateUploadSlot("forward", { error: undefined });
                }}
                placeholder="Upload or provide a server-accessible FASTA path"
                required
              />
              {renderUploadSection("forward")}
            </div>

            {formState.inputType === "paired" ? (
              <div className="form-control">
                <label htmlFor="reversePath">Reverse reads (R2)</label>
                <input
                  id="reversePath"
                  value={formState.reversePath}
                  onChange={(event) => {
                    const value = event.target.value;
                    setFormState((state) => ({ ...state, reversePath: value }));
                    updateUploadSlot("reverse", { error: undefined });
                  }}
                  placeholder="Upload or provide a server-accessible FASTA path"
                  required
                />
                {renderUploadSection("reverse")}
              </div>
            ) : null}

            <div className="form-control">
              <label htmlFor="outputDir">Output location</label>
              <input
                id="outputDir"
                value={formState.outputDir}
                onChange={(event) => setFormState((state) => ({ ...state, outputDir: event.target.value }))}
                placeholder="results"
              />
            </div>

            <div className="form-control" style={{ gridColumn: "1 / -1" }}>
              <label htmlFor="notes">Notes</label>
              <textarea id="notes" rows={3} placeholder="Describe the environmental context or hypothesis (optional)" />
            </div>

            <div style={{ gridColumn: "1 / -1", display: "flex", gap: "16px" }}>
              <button
                type="submit"
                className="primary-button"
                disabled={
                  submitting ||
                  uploadState.forward.uploading ||
                  (formState.inputType === "paired" && uploadState.reverse.uploading)
                }
              >
                <FiPlay />
                {submitting ? "Launching..." : "Start analysis"}
              </button>
              {error ? <div style={{ color: "#ff7b89", alignSelf: "center" }}>{error}</div> : null}
            </div>
          </form>
        </section>
      )}

      {!shouldLockSingleRun ? (
        <section className="card" style={{ display: "grid", gap: "18px" }}>
          <div className="section-title">
            <h3>Latest launch status</h3>
            <span>Live run telemetry from backend processing</span>
          </div>
          {latestRun ? (
            <div style={{ display: "grid", gap: "12px" }}>
              <div>
                <div className="stat-card__label">Sample</div>
                <div className="stat-card__value">{latestRun.sample_id}</div>
              </div>
              <div style={{ display: "grid", gap: "12px", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                <div className="form-control">
                  <label>Started</label>
                  <span>{latestRun.start_time ?? "--"}</span>
                </div>
                <div className="form-control">
                  <label>Status</label>
                  {(() => {
                    const state = getRunState(latestRun);
                    if (state === "completed") {
                      return <span className="status-pill status-pill--success">Completed</span>;
                    }
                    if (state === "running") {
                      return <span className="status-pill status-pill--pending">Running</span>;
                    }
                    if (state === "queued") {
                      return <span className="status-pill status-pill--pending">Queued</span>;
                    }
                    if (state === "pending") {
                      return <span className="status-pill status-pill--pending">Pending</span>;
                    }
                    return <span className="status-pill status-pill--error">Failed</span>;
                  })()}
                </div>
                <div className="form-control">
                  <label>Output directory</label>
                  <span>{latestRun.output_dir}</span>
                </div>
              </div>
              {(() => {
                const state = getRunState(latestRun);
                if (state === "running" || state === "queued" || state === "pending") {
                  return (
                    <div style={{ display: "grid", gap: "8px" }}>
                      <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>{latestRunMessage}</div>
                      {latestRun.current_step ? (
                        <div style={{ fontSize: "12px", color: "var(--text-muted)", textTransform: "capitalize" }}>
                          Step: {latestRun.current_step.replace(/_/g, " ")}
                        </div>
                      ) : null}
                      <div style={{ height: "8px", width: "100%", borderRadius: "999px", background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                        <div
                          style={{
                            height: "100%",
                            width: `${Math.max(0, Math.min(100, latestRun.progress ?? 0))}%`,
                            background: "linear-gradient(90deg, var(--accent), #43d29d)",
                            transition: "width 300ms ease"
                          }}
                        />
                      </div>
                      <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                        {Math.max(0, Math.min(100, latestRun.progress ?? 0)).toFixed(0)}% complete
                      </div>
                    </div>
                  );
                }
                return null;
              })()}
              {(() => {
                const state = getRunState(latestRun);
                if (state === "failed" && latestRun.error) {
                  return <div style={{ color: "#ff7b89", fontSize: "13px" }}>{latestRun.error}</div>;
                }
                return null;
              })()}
              {(() => {
                const state = getRunState(latestRun);
                if (state === "completed") {
                  return (
                    <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                      <span className="status-pill status-pill--success">Run completed</span>
                      <Link to={`/results/${latestRun.sample_id}`} className="secondary-button">
                        View details
                      </Link>
                    </div>
                  );
                }
                return null;
              })()}
            </div>
          ) : (
            <div className="empty-state">
              Launch a run to see live tracking or connect the API endpoint at VITE_API_URL.
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
};

export default SingleRun;
