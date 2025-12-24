import { ReactNode, useMemo } from "react";
import { useParams } from "react-router-dom";
import { FiCheckCircle, FiClock, FiDownloadCloud, FiFileText, FiTrendingUp, FiXCircle } from "react-icons/fi";
import api from "../services/api";
import { useAsyncData } from "../hooks/useAsyncData";
import type { PipelineRun, PipelineStep } from "../types/pipeline";

type ArtifactDescriptor = {
  id: string;
  label: string;
  description: string;
  path: string;
  mode?: "inline" | "attachment";
  icon: ReactNode;
  downloadName?: string;
};

const normalizeRunStatus = (status?: string, success?: boolean) => {
  const state = (status ?? (success ? "completed" : "failed")).toLowerCase();
  if (state === "completed" || state === "running" || state === "queued" || state === "pending") {
    return state;
  }
  return "failed";
};

const formatStatusLabel = (state: string) => state.charAt(0).toUpperCase() + state.slice(1);

const statusClass = (status: string) => {
  const normalized = status.toLowerCase();
  switch (normalized) {
    case "completed":
      return "status-pill status-pill--success";
    case "failed":
      return "status-pill status-pill--error";
    case "running":
      return "status-pill";
    default:
      return "status-pill status-pill--pending";
  }
};

const RunDetails = () => {
  const { runId } = useParams<{ runId: string }>();
  const { data: run, loading, error } = useAsyncData<PipelineRun>(
    () => api.fetchRunDetails(runId ?? ""),
    [runId],
    { immediate: Boolean(runId) }
  );

  const artifacts = useMemo(() => {
    if (!run) {
      return [] as ArtifactDescriptor[];
    }

    const items: ArtifactDescriptor[] = [];

    const reportStep = run.pipeline_steps.find((step) => step.step === "report_generation");
    const reportResults = reportStep?.results as { report_file?: string; report_format?: string } | undefined;
    if (reportResults?.report_file) {
      items.push({
        id: "sample-report",
        label: "Sample report",
        description: "Generated HTML summary with taxonomy and diversity metrics.",
        path: reportResults.report_file,
        mode: "inline",
        icon: <FiFileText size={24} color="var(--accent)" />
      });
    }

    const abundanceStep = run.pipeline_steps.find((step) => step.step === "abundance_quantification");
    const abundanceResults = abundanceStep?.results as {
      abundance_file?: string;
      normalized_file?: string;
      diversity_file?: string;
    } | undefined;

    if (abundanceResults?.abundance_file) {
      items.push({
        id: "abundance-matrix",
        label: "Abundance matrix",
        description: "CSV with raw counts for downstream analyses.",
        path: abundanceResults.abundance_file,
        icon: <FiTrendingUp size={24} color="var(--accent)" />,
        downloadName: "abundance_matrix.csv"
      });
    }

    if (abundanceResults?.normalized_file) {
      items.push({
        id: "normalized-abundance",
        label: "Normalized abundance",
        description: "Normalized abundance values ready for comparative studies.",
        path: abundanceResults.normalized_file,
        icon: <FiDownloadCloud size={24} color="var(--accent)" />,
        downloadName: "normalized_abundance.csv"
      });
    }

    if (abundanceResults?.diversity_file) {
      items.push({
        id: "diversity-metrics",
        label: "Diversity metrics",
        description: "Diversity indices exported from the pipeline run.",
        path: abundanceResults.diversity_file,
        icon: <FiDownloadCloud size={24} color="var(--accent)" />,
        downloadName: "diversity_metrics.csv"
      });
    }

    const taxonomyStep = run.pipeline_steps.find((step) => step.step === "taxonomic_classification");
    const taxonomyResults = taxonomyStep?.results as { detailed_file?: string; summary_file?: string } | undefined;
    if (taxonomyResults?.detailed_file) {
      items.push({
        id: "taxonomic-assignments",
        label: "Taxonomic assignments",
        description: "Detailed CSV of taxonomic calls for each ASV.",
        path: taxonomyResults.detailed_file,
        icon: <FiDownloadCloud size={24} color="var(--accent)" />,
        downloadName: "taxonomic_assignments.csv"
      });
    }
    if (taxonomyResults?.summary_file) {
      items.push({
        id: "taxonomy-summary",
        label: "Taxonomy summary",
        description: "JSON summary of classifications and confidence scores.",
        path: taxonomyResults.summary_file,
        icon: <FiDownloadCloud size={24} color="var(--accent)" />,
        downloadName: "taxonomy_summary.json"
      });
    }

    return items;
  }, [run]);

  const summaryCards = useMemo(() => {
    if (!run) {
      return [];
    }
    const runState = normalizeRunStatus(run.status, run.success);
    const taxStep = run.pipeline_steps.find((step) => step.step === "taxonomic_classification");
    const abundanceStep = run.pipeline_steps.find((step) => step.step === "abundance_quantification");
    const classification = taxStep?.results as { total_classified?: number; mean_confidence?: number } | undefined;
    const abundance = abundanceStep?.results as { total_reads?: number; total_asvs?: number } | undefined;

    return [
      {
        label: "Status",
        value: formatStatusLabel(runState)
      },
      {
        label: "Total reads",
        value: abundance?.total_reads ? abundance.total_reads.toLocaleString() : "--"
      },
      {
        label: "ASVs",
        value: abundance?.total_asvs?.toString() ?? "--"
      },
      {
        label: "Classified",
        value: classification?.total_classified?.toString() ?? "--"
      },
      {
        label: "Mean confidence",
        value: classification?.mean_confidence ? `${classification.mean_confidence.toFixed(1)}%` : "--"
      }
    ];
  }, [run]);

  if (!runId) {
    return <div className="empty-state">Select a run from the results page to inspect details.</div>;
  }

  if (loading) {
    return <div className="empty-state">Loading run details...</div>;
  }

  if (error || !run) {
    return <div className="empty-state">Unable to load run data. Confirm the run identifier and API endpoint.</div>;
  }

  const runState = normalizeRunStatus(run.status, run.success);
  const isSuccess = runState === "completed";
  const isPending = runState === "running" || runState === "queued" || runState === "pending";
  const completionHeadline = isSuccess
    ? "Run finished successfully"
    : isPending
    ? "Run in progress"
    : "Action required";
  const completionMessage = isSuccess
    ? "All pipeline stages have completed. Review the report or export artifacts."
    : isPending
    ? "Pipeline execution is underway. Refresh to sync the latest telemetry."
    : run.error ?? "Unknown error";
  const StatusIcon = isSuccess ? FiCheckCircle : isPending ? FiClock : FiXCircle;
  const statusColor = isSuccess ? "var(--accent)" : isPending ? "var(--text-muted)" : "#ff7b89";

  const handleArtifactClick = (artifact: ArtifactDescriptor) => {
    api.openFile(artifact.path, {
      mode: artifact.mode ?? "attachment",
      downloadName: artifact.downloadName
    });
  };

  return (
    <div className="page-grid" style={{ gap: "24px", maxWidth: "1100px" }}>
      <section className="card" style={{ display: "grid", gap: "16px" }}>
        <div className="section-title">
          <h3>Run overview</h3>
          <span>Sample {run.sample_id}</span>
        </div>
        <div className="stats-grid">
          {summaryCards.map((card) => (
            <div key={card.label} className="stat-card">
              <div className="stat-card__label">{card.label}</div>
              <div className="stat-card__value">{card.value}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "grid", gap: "12px", fontSize: "14px" }}>
          <div><strong>Input files:</strong> {Array.isArray(run.input_files) ? run.input_files.join(", ") : run.input_files}</div>
          <div><strong>Duration:</strong> {run.processing_time ? `${Math.round(run.processing_time / 60)} minutes` : "--"}</div>
          <div><strong>Output directory:</strong> {run.output_dir}</div>
        </div>
      </section>

      <section className="card" style={{ display: "grid", gap: "18px" }}>
        <div className="section-title">
          <h3>Processing timeline</h3>
          <span>Tracked through `DeepSeaEDNAPipeline`</span>
        </div>
        <div className="page-grid" style={{ gap: "16px" }}>
          {run.pipeline_steps.map((step: PipelineStep) => (
            <div key={step.step} className="card" style={{ padding: "18px", display: "grid", gap: "12px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontWeight: 600, textTransform: "capitalize" }}>{step.step.replace(/_/g, " ")}</div>
                <span className={statusClass(step.status)}>{step.status}</span>
              </div>
              <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                {step.status === "completed"
                  ? "Completed successfully"
                  : step.status === "failed"
                  ? "Check logs for stack trace"
                  : "Awaiting execution"}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card" style={{ display: "grid", gap: "16px" }}>
        <div className="section-title">
          <h3>Artifacts</h3>
          <span>Download textual and HTML reports</span>
        </div>
        {artifacts.length === 0 ? (
          <div className="empty-state">No downloadable artifacts are available for this run.</div>
        ) : (
          <div className="page-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px" }}>
            {artifacts.map((artifact) => (
              <div key={artifact.id} className="card card--interactive" style={{ padding: "18px", display: "grid", gap: "12px" }}>
                {artifact.icon}
                <div>
                  <div style={{ fontWeight: 600 }}>{artifact.label}</div>
                  <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>{artifact.description}</div>
                </div>
                <button type="button" className="secondary-button" onClick={() => handleArtifactClick(artifact)}>
                  <FiDownloadCloud />
                  {artifact.mode === "inline" ? "Open" : "Download"}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card" style={{ display: "grid", gap: "16px" }}>
        <div className="section-title">
          <h3>Completion status</h3>
          <span>{completionHeadline}</span>
        </div>
        <div style={{ display: "flex", gap: "14px", alignItems: "center" }}>
          <StatusIcon size={32} color={statusColor} />
          <div style={{ color: "var(--text-secondary)" }}>{completionMessage}</div>
        </div>
      </section>
    </div>
  );
};

export default RunDetails;
