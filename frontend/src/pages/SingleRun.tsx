import { ChangeEvent, DragEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";
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
  inputType: "paired",
  forwardPath: "",
  reversePath: "",
  outputDir: "results"
};

const allowedFastqExtensions = [".fastq", ".fq", ".fastq.gz", ".fq.gz"] as const;
type UploadSlot = "forward" | "reverse";

interface UploadSlotState {
  uploading: boolean;
  name?: string;
  error?: string;
  dragging?: boolean;
}

const SingleRun = () => {
  const [formState, setFormState] = useState<RunFormState>(defaultState);
  const [submitting, setSubmitting] = useState(false);
  const [latestRun, setLatestRun] = useState<PipelineRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadState, setUploadState] = useState<{ forward: UploadSlotState; reverse: UploadSlotState }>({
    forward: { uploading: false },
    reverse: { uploading: false }
  });
  const forwardFileInputRef = useRef<HTMLInputElement | null>(null);
  const reverseFileInputRef = useRef<HTMLInputElement | null>(null);
  const isMountedRef = useRef(true);
  const pollingRunIdRef = useRef<string | null>(null);

  useEffect(() => () => {
    isMountedRef.current = false;
    pollingRunIdRef.current = null;
  }, []);

  const isValidFastq = (filename: string) =>
    allowedFastqExtensions.some((extension) => filename.toLowerCase().endsWith(extension));

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
    if (!isValidFastq(file.name)) {
      updateUploadSlot(slot, {
        uploading: false,
        name: undefined,
        dragging: false,
        error: "Unsupported file type. Upload .fastq, .fq, or .fastq.gz files."
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
              {slotState.uploading ? "Uploading..." : "Drop FASTQ or click to choose"}
            </div>
            <div className="upload-dropzone__subtitle">
              {slotState.name
                ? `Selected: ${slotState.name}`
                : "Accepted formats: .fastq, .fq, .fastq.gz"}
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
          accept=".fastq,.fq,.fastq.gz,.fq.gz"
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
    if (!formState.forwardPath || (formState.inputType === "paired" && !formState.reversePath)) {
      setError("Provide a server-accessible FASTQ path for all required reads.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        sampleId: formState.sampleId,
        inputType: formState.inputType,
        files:
          formState.inputType === "paired"
            ? [formState.forwardPath, formState.reversePath]
            : [formState.forwardPath],
        configOverrides: formState.outputDir ? { "output.dir": formState.outputDir } : undefined
      };
      const run = await api.triggerRun(payload);
      setLatestRun(run);
      pollingRunIdRef.current = run.sample_id;
      void pollRunStatus(run.sample_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
    } finally {
      setSubmitting(false);
    }
  };

  const pollRunStatus = useCallback(async (runId: string) => {
    const maxAttempts = 60;
    let attempts = 0;

    while (isMountedRef.current && pollingRunIdRef.current === runId && attempts < maxAttempts) {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      if (!isMountedRef.current || pollingRunIdRef.current !== runId) {
        return;
      }

      try {
        const refreshed = await api.fetchRunDetails(runId);
        if (!isMountedRef.current) {
          return;
        }
        setLatestRun(refreshed);
        const state = (refreshed.status ?? (refreshed.success ? "completed" : "failed")).toLowerCase();
        if (state === "completed" || state === "failed") {
          pollingRunIdRef.current = null;
          window.dispatchEvent(new CustomEvent("app:refresh-data"));
          return;
        }
      } catch (pollError) {
        if (!isMountedRef.current) {
          return;
        }
        setError((prev) => prev ?? (pollError instanceof Error ? pollError.message : "Failed to poll run status"));
        return;
      }

      attempts += 1;
    }

    if (isMountedRef.current && attempts >= maxAttempts) {
      setError((prev) => prev ?? "Run is still in progress. Check the Results page for the latest status.");
    }
  }, []);

  return (
    <div className="page-grid" style={{ gap: "28px", maxWidth: "1100px" }}>
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
              <option value="single">Single-end FASTQ</option>
              <option value="paired">Paired-end FASTQ</option>
            </select>
          </div>

          <div className="form-control">
            <label htmlFor="forwardPath">
              {formState.inputType === "paired" ? "Forward reads (R1)" : "FASTQ file"}
            </label>
            <input
              id="forwardPath"
              value={formState.forwardPath}
              onChange={(event) => {
                const value = event.target.value;
                setFormState((state) => ({ ...state, forwardPath: value }));
                updateUploadSlot("forward", { error: undefined });
              }}
              placeholder="Upload or provide a server-accessible FASTQ path"
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
                placeholder="Upload or provide a server-accessible FASTQ path"
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

      <section className="card" style={{ display: "grid", gap: "18px" }}>
        <div className="section-title">
          <h3>Latest launch status</h3>
          <span>Mock response preview until backend is connected</span>
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
                  const state = (latestRun.status ?? (latestRun.success ? "completed" : "failed")).toLowerCase();
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
              const state = (latestRun.status ?? (latestRun.success ? "completed" : "failed")).toLowerCase();
              if (state === "failed" && latestRun.error) {
                return <div style={{ color: "#ff7b89", fontSize: "13px" }}>{latestRun.error}</div>;
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
    </div>
  );
};

export default SingleRun;
