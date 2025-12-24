import { ChangeEvent, DragEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { FiLayers, FiPlus, FiTrash2, FiUploadCloud } from "react-icons/fi";
import clsx from "clsx";
import api from "../services/api";
import type { BatchRun, RunRequestPayload } from "../types/pipeline";

interface BatchSample extends RunRequestPayload {
  id: string;
}

const allowedFastqExtensions = [".fastq", ".fq", ".fastq.gz", ".fq.gz"] as const;
type UploadSlot = "forward" | "reverse";

interface UploadSlotState {
  uploading: boolean;
  name?: string;
  error?: string;
  dragging?: boolean;
}

type SampleUploadState = Record<UploadSlot, UploadSlotState>;

const createSlotState = (): UploadSlotState => ({ uploading: false, dragging: false });
const defaultUploadState = (): SampleUploadState => ({ forward: createSlotState(), reverse: createSlotState() });

const createSample = (index: number): BatchSample => {
  const fallbackId = `sample-${index}-${Math.random().toString(16).slice(2, 10)}`;
  const generatedId = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : fallbackId;
  return {
    id: generatedId,
    sampleId: `sample_${index + 1}`,
    inputType: "paired",
    files: ["", ""],
    configOverrides: {}
  };
};

const BatchRuns = () => {
  const initialSamplesRef = useRef<BatchSample[] | null>(null);
  if (!initialSamplesRef.current) {
    initialSamplesRef.current = [createSample(0), createSample(1)];
  }

  const [samples, setSamples] = useState<BatchSample[]>(() => [...(initialSamplesRef.current ?? [])]);
  const [uploadState, setUploadState] = useState<Record<string, SampleUploadState>>(() => {
    const initial: Record<string, SampleUploadState> = {};
    for (const sample of initialSamplesRef.current ?? []) {
      initial[sample.id] = defaultUploadState();
    }
    return initial;
  });
  const [submitting, setSubmitting] = useState(false);
  const [latestBatch, setLatestBatch] = useState<BatchRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRefs = useRef<Record<string, Record<UploadSlot, HTMLInputElement | null>>>({});
  const isMountedRef = useRef(true);
  const pollingBatchIdRef = useRef<string | null>(null);

  useEffect(() => () => {
    isMountedRef.current = false;
    pollingBatchIdRef.current = null;
  }, []);

  useEffect(() => {
    const sampleIds = new Set(samples.map((sample) => sample.id));

    setUploadState((state) => {
      let changed = false;
      const next: Record<string, SampleUploadState> = { ...state };

      for (const sample of samples) {
        if (!next[sample.id]) {
          next[sample.id] = defaultUploadState();
          changed = true;
        }
      }

      for (const id of Object.keys(next)) {
        if (!sampleIds.has(id)) {
          delete next[id];
          changed = true;
        }
      }

      return changed ? next : state;
    });

    for (const id of Object.keys(fileInputRefs.current)) {
      if (!sampleIds.has(id)) {
        delete fileInputRefs.current[id];
      }
    }
  }, [samples]);

  const isValidFastq = (filename: string) =>
    allowedFastqExtensions.some((extension) => filename.toLowerCase().endsWith(extension));

  const updateUploadSlot = (sampleId: string, slot: UploadSlot, partial: Partial<UploadSlotState>) => {
    setUploadState((state) => {
      const sampleState = state[sampleId];
      if (!sampleState) {
        return state;
      }

      const currentSlot = sampleState[slot];
      const nextSlot: UploadSlotState = { ...currentSlot, ...partial };

      if (
        currentSlot.uploading === nextSlot.uploading &&
        currentSlot.name === nextSlot.name &&
        currentSlot.error === nextSlot.error &&
        currentSlot.dragging === nextSlot.dragging
      ) {
        return state;
      }

      return {
        ...state,
        [sampleId]: {
          ...sampleState,
          [slot]: nextSlot
        }
      };
    });
  };

  const getInputRef = (sampleId: string, slot: UploadSlot) => {
    const sampleRefs = fileInputRefs.current[sampleId];
    return sampleRefs ? sampleRefs[slot] : null;
  };

  const openFileDialog = (sampleId: string, slot: UploadSlot) => {
    const ref = getInputRef(sampleId, slot);
    ref?.click();
  };

  const updateSample = (id: string, partial: Partial<BatchSample>) => {
    setSamples((current) => current.map((sample) => (sample.id === id ? { ...sample, ...partial } : sample)));
  };

  const handleManualPathChange = (sampleId: string, slot: UploadSlot, value: string) => {
    setSamples((current) =>
      current.map((sample) => {
        if (sample.id !== sampleId) {
          return sample;
        }

        const [forwardFile = "", reverseFile = ""] = sample.files;

        if (sample.inputType === "paired") {
          const nextFiles: string[] = [
            slot === "forward" ? value : forwardFile,
            slot === "reverse" ? value : reverseFile
          ];
          return { ...sample, files: nextFiles };
        }

        return { ...sample, files: [value] };
      })
    );
    updateUploadSlot(sampleId, slot, { error: undefined, name: undefined });
  };

  const handleFileUpload = async (sampleId: string, slot: UploadSlot, file: File) => {
    if (!isValidFastq(file.name)) {
      updateUploadSlot(sampleId, slot, {
        uploading: false,
        name: undefined,
        error: "Unsupported file type. Upload .fastq, .fq, or .fastq.gz files.",
        dragging: false
      });
      return;
    }

    updateUploadSlot(sampleId, slot, {
      uploading: true,
      name: file.name,
      error: undefined,
      dragging: false
    });

    try {
      const result = await api.uploadRunFile(file);
      const savedPath = result.relative_path ?? result.file_path;

      setSamples((current) =>
        current.map((sample) => {
          if (sample.id !== sampleId) {
            return sample;
          }

          const [forwardFile = "", reverseFile = ""] = sample.files;

          if (sample.inputType === "paired") {
            const nextFiles: string[] = [
              slot === "forward" ? savedPath : forwardFile,
              slot === "reverse" ? savedPath : reverseFile
            ];
            return { ...sample, files: nextFiles };
          }

          return { ...sample, files: [savedPath] };
        })
      );

      updateUploadSlot(sampleId, slot, {
        uploading: false,
        name: file.name,
        error: undefined,
        dragging: false
      });
    } catch (uploadError) {
      const message = uploadError instanceof Error ? uploadError.message : "Upload failed";
      updateUploadSlot(sampleId, slot, {
        uploading: false,
        error: message,
        dragging: false
      });
    }
  };

  const handleFileSelection = async (
    event: ChangeEvent<HTMLInputElement>,
    sampleId: string,
    slot: UploadSlot
  ) => {
    const file = event.target.files?.[0];
    if (file) {
      await handleFileUpload(sampleId, slot, file);
    }
    event.target.value = "";
  };

  const handleDragState = (
    event: DragEvent<HTMLDivElement>,
    sampleId: string,
    slot: UploadSlot,
    active: boolean
  ) => {
    event.preventDefault();
    event.stopPropagation();
    updateUploadSlot(sampleId, slot, { dragging: active });
  };

  const handleDrop = async (event: DragEvent<HTMLDivElement>, sampleId: string, slot: UploadSlot) => {
    event.preventDefault();
    event.stopPropagation();
    updateUploadSlot(sampleId, slot, { dragging: false });

    const file = event.dataTransfer?.files?.[0];
    if (file) {
      await handleFileUpload(sampleId, slot, file);
    }
  };

  const handleFormatChange = (sampleId: string, value: BatchSample["inputType"]) => {
    setSamples((current) =>
      current.map((sample) => {
        if (sample.id !== sampleId) {
          return sample;
        }

        const [forwardFile = "", reverseFile = ""] = sample.files;
        return {
          ...sample,
          inputType: value,
          files: value === "paired" ? [forwardFile, reverseFile || ""] : [forwardFile]
        };
      })
    );

    if (value === "single") {
      updateUploadSlot(sampleId, "reverse", {
        uploading: false,
        dragging: false,
        name: undefined,
        error: undefined
      });
    }
  };

  const renderUploadSection = (sample: BatchSample, slot: UploadSlot) => {
    const slotState = uploadState[sample.id]?.[slot] ?? { uploading: false, dragging: false };
    const pathIndex = slot === "forward" ? 0 : 1;
    const currentPath =
      sample.inputType === "paired"
        ? sample.files[pathIndex] ?? ""
        : sample.files[0] ?? "";

    return (
      <div className="upload-dropzone-wrapper">
        <div
          className={clsx("upload-dropzone", {
            "upload-dropzone--drag": Boolean(slotState.dragging),
            "upload-dropzone--uploading": slotState.uploading
          })}
          onDragOver={(event) => event.preventDefault()}
          onDragEnter={(event) => handleDragState(event, sample.id, slot, true)}
          onDragLeave={(event) => handleDragState(event, sample.id, slot, false)}
          onDrop={(event) => void handleDrop(event, sample.id, slot)}
          onClick={() => openFileDialog(sample.id, slot)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              openFileDialog(sample.id, slot);
            }
          }}
          role="button"
          tabIndex={0}
          aria-label={`Upload ${slot === "forward" ? "forward" : "reverse"} FASTQ for ${
            sample.sampleId || "sample"
          }`}
        >
          <div className="upload-dropzone__icon">
            <FiUploadCloud />
          </div>
          <div className="upload-dropzone__content">
            <div className="upload-dropzone__title">
              {slotState.uploading ? "Uploading..." : "Drop FASTQ or click to choose"}
            </div>
            <div className="upload-dropzone__subtitle">
              {slotState.name ? `Selected: ${slotState.name}` : "Accepted formats: .fastq, .fq, .fastq.gz"}
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
          ref={(element) => {
            if (!fileInputRefs.current[sample.id]) {
              fileInputRefs.current[sample.id] = { forward: null, reverse: null };
            }
            fileInputRefs.current[sample.id][slot] = element;
          }}
          type="file"
          accept=".fastq,.fq,.fastq.gz,.fq.gz"
          style={{ display: "none" }}
          onChange={(event) => void handleFileSelection(event, sample.id, slot)}
        />
        {slotState.error ? (
          <div style={{ color: "#ff7b89", fontSize: "13px" }}>{slotState.error}</div>
        ) : null}
      </div>
    );
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const hasPendingUploads = Object.values(uploadState).some(
      (state) => state.forward.uploading || state.reverse.uploading
    );
    if (hasPendingUploads) {
      setError("Wait for all uploads to finish before scheduling.");
      return;
    }

    setSubmitting(true);
    setError(null);
    const invalidSample = samples.find((sample) => !sample.sampleId || sample.files.some((file) => !file));
    if (invalidSample) {
      setSubmitting(false);
      setError("All samples must include IDs and FASTQ file paths before scheduling.");
      return;
    }
    try {
      const payload = {
        runs: samples.map((sample) => ({
          sampleId: sample.sampleId,
          inputType: sample.inputType,
          files: sample.files,
          configOverrides: sample.configOverrides
        }))
      };
      const batch = await api.triggerBatchRun(payload);
      setLatestBatch(batch);
      pollingBatchIdRef.current = batch.batch_id;
      void pollBatchStatus(batch.batch_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start batch run");
    } finally {
      setSubmitting(false);
    }
  };

  const pollBatchStatus = useCallback(async (batchId: string) => {
    const maxAttempts = 120;
    let attempts = 0;

    while (isMountedRef.current && pollingBatchIdRef.current === batchId && attempts < maxAttempts) {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      if (!isMountedRef.current || pollingBatchIdRef.current !== batchId) {
        return;
      }

      try {
        const refreshed = await api.fetchBatchDetails(batchId);
        if (!isMountedRef.current) {
          return;
        }
        setLatestBatch(refreshed);
        const state = (refreshed.status ?? (refreshed.failed_samples ? "failed" : "completed")).toLowerCase();
        if (state === "completed" || state === "failed") {
          pollingBatchIdRef.current = null;
          window.dispatchEvent(new CustomEvent("app:refresh-data"));
          return;
        }
      } catch (pollError) {
        if (!isMountedRef.current) {
          return;
        }
        setError((prev) => prev ?? (pollError instanceof Error ? pollError.message : "Failed to poll batch status"));
        return;
      }

      attempts += 1;
    }

    if (isMountedRef.current && attempts >= maxAttempts) {
      setError((prev) => prev ?? "Batch is still running. Revisit the results page for updates.");
    }
  }, []);

  const isAnyUploading = Object.values(uploadState).some(
    (state) => state.forward.uploading || state.reverse.uploading
  );

  return (
    <div className="page-grid" style={{ gap: "28px" }}>
      <section className="card" style={{ display: "grid", gap: "18px" }}>
        <div className="section-title">
          <h3>Batch orchestration</h3>
          <span>Queue multiple samples and let the scheduler take over</span>
        </div>
        <form onSubmit={handleSubmit} className="page-grid" style={{ gap: "16px" }}>
          {samples.map((sample, index) => (
            <div key={sample.id} className="card" style={{ padding: "18px", display: "grid", gap: "14px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div className="tag">Sample {index + 1}</div>
                {samples.length > 1 ? (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setSamples((current) => current.filter((item) => item.id !== sample.id))}
                  >
                    <FiTrash2 /> Remove
                  </button>
                ) : null}
              </div>
              <div className="form-grid" style={{ gap: "16px" }}>
                <div className="form-control">
                  <label>Sample ID</label>
                  <input
                    value={sample.sampleId}
                    onChange={(event) => updateSample(sample.id, { sampleId: event.target.value })}
                    required
                  />
                </div>
                <div className="form-control">
                  <label>Read format</label>
                  <select
                    value={sample.inputType}
                    onChange={(event) =>
                      handleFormatChange(sample.id, event.target.value as BatchSample["inputType"])
                    }
                  >
                    <option value="single">Single-end</option>
                    <option value="paired">Paired-end</option>
                  </select>
                </div>
                <div className="form-control">
                  <label>{sample.inputType === "paired" ? "Forward reads" : "FASTQ"}</label>
                  <input
                    value={sample.files[0] ?? ""}
                    onChange={(event) => handleManualPathChange(sample.id, "forward", event.target.value)}
                    placeholder="Upload or provide a server-accessible FASTQ path"
                    required
                  />
                  {renderUploadSection(sample, "forward")}
                </div>
                {sample.inputType === "paired" ? (
                  <div className="form-control">
                    <label>Reverse reads</label>
                    <input
                      value={sample.files[1] ?? ""}
                      onChange={(event) => handleManualPathChange(sample.id, "reverse", event.target.value)}
                      placeholder="Upload or provide a server-accessible FASTQ path"
                      required
                    />
                    {renderUploadSection(sample, "reverse")}
                  </div>
                ) : null}
              </div>
            </div>
          ))}

          <div style={{ display: "flex", gap: "12px" }}>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setSamples((current) => [...current, createSample(current.length)])}
            >
              <FiPlus /> Add sample
            </button>
            <button type="submit" className="primary-button" disabled={submitting || isAnyUploading}>
              <FiLayers />
              {submitting ? "Scheduling..." : "Schedule batch"}
            </button>
            {error ? <div style={{ color: "#ff7b89", alignSelf: "center" }}>{error}</div> : null}
          </div>
        </form>
      </section>

      <section className="card" style={{ display: "grid", gap: "12px" }}>
        <div className="section-title">
          <h3>Latest batch telemetry</h3>
          <span>Status polled directly from the API</span>
        </div>
        {latestBatch ? (
          <div style={{ display: "grid", gap: "12px" }}>
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-card__label">Batch ID</div>
                <div className="stat-card__value">{latestBatch.batch_id}</div>
              </div>
              <div className="stat-card">
                <div className="stat-card__label">Success</div>
                <div className="stat-card__value">
                  {latestBatch.successful_samples}/{latestBatch.total_samples}
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-card__label">Processing time</div>
                <div className="stat-card__value">{Math.round((latestBatch.total_processing_time ?? 0) / 60)} min</div>
              </div>
              <div className="stat-card">
                <div className="stat-card__label">Success rate</div>
                <div className="stat-card__value">
                  {latestBatch.summary_report?.success_rate
                    ? `${Math.round(latestBatch.summary_report.success_rate * 100)}%`
                    : "--"}
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-card__label">Status</div>
                <div className="stat-card__value">
                  {(latestBatch.status ?? (latestBatch.failed_samples ? "failed" : "completed")).toUpperCase()}
                </div>
              </div>
            </div>
            {latestBatch.error ? (
              <div style={{ color: "#ff7b89", fontSize: "13px" }}>{latestBatch.error}</div>
            ) : null}
          </div>
        ) : (
          <div className="empty-state">
            Schedule a batch to monitor multi-sample throughput and failure budgets.
          </div>
        )}
      </section>
    </div>
  );
};

export default BatchRuns;
