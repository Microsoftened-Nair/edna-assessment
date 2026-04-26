import { ReactNode, useMemo } from "react";
import { useParams } from "react-router-dom";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid
} from "recharts";

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

type ClassificationPrediction = {
  sequence_id?: string;
  kingdom?: string;
  phylum?: string;
  genus?: string;
  species?: string;
  confidence?: number;
  method?: string;
};

type DistributionEntry = {
  name: string;
  value: number;
};

const CHART_COLORS = [
  "#2be38b",
  "#22c67a",
  "#1ca769",
  "#1a8a5a",
  "#2f9a78",
  "#37b18b",
  "#4cc89f",
  "#63ddbb"
];

const toDistributionData = (distribution?: Record<string, number>, limit = 10): DistributionEntry[] => {
  if (!distribution) {
    return [];
  }

  return Object.entries(distribution)
    .map(([name, value]) => ({ name, value: Number(value) || 0 }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
};

const formatPct = (value: number, total: number): string => {
  if (!total) {
    return "0.0%";
  }
  return `${((value / total) * 100).toFixed(1)}%`;
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
    { immediate: Boolean(runId), pollIntervalMs: 4000 }
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

    const embeddingStep = run.pipeline_steps.find((step) => step.step === "embedding_generation");
    const embeddingResults = embeddingStep?.results as {
      dnabert2_embeddings_file?: string;
    } | undefined;
    if (embeddingResults?.dnabert2_embeddings_file) {
      items.push({
        id: "dnabert2-embeddings",
        label: "DNABERT2 embeddings",
        description: "Compressed embeddings generated by pretrained DNABERT2 for this run.",
        path: embeddingResults.dnabert2_embeddings_file,
        icon: <FiDownloadCloud size={24} color="var(--accent)" />,
        downloadName: "dnabert2_embeddings.npz"
      });
    }

    const taxonomyStep = run.pipeline_steps.find((step) => step.step === "taxonomic_classification");
    const taxonomyResults = taxonomyStep?.results as {
      detailed_file?: string;
      summary_file?: string;
      predictions_file?: string;
    } | undefined;
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
    if (taxonomyResults?.predictions_file) {
      items.push({
        id: "classification-predictions",
        label: "Classification predictions",
        description: "JSON list with per-sequence taxonomic assignments and confidence scores.",
        path: taxonomyResults.predictions_file,
        icon: <FiDownloadCloud size={24} color="var(--accent)" />,
        downloadName: "taxonomic_predictions.json"
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
    const classification = taxStep?.results as {
      total_classified?: number;
      mean_confidence?: number;
      classification_mode?: string;
    } | undefined;
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
      },
      {
        label: "Classification mode",
        value: classification?.classification_mode ?? "--"
      }
    ];
  }, [run]);

  const taxonomyResults = useMemo(() => {
    if (!run) {
      return undefined;
    }
    const taxStep = run.pipeline_steps.find((step) => step.step === "taxonomic_classification");
    return taxStep?.results as {
      total_classified?: number;
      mean_confidence?: number;
      classification_mode?: string;
      classifier?: string;
      phylum_distribution?: Record<string, number>;
      genus_distribution?: Record<string, number>;
      species_distribution?: Record<string, number>;
      confidence_distribution?: Record<string, number>;
      top_predictions?: ClassificationPrediction[];
    } | undefined;
  }, [run]);

  const phylumData = useMemo(
    () => toDistributionData(taxonomyResults?.phylum_distribution, 10),
    [taxonomyResults?.phylum_distribution]
  );
  const genusData = useMemo(
    () => toDistributionData(taxonomyResults?.genus_distribution, 10),
    [taxonomyResults?.genus_distribution]
  );

  const confidenceData = useMemo(() => {
    const distribution = taxonomyResults?.confidence_distribution;
    if (!distribution) {
      return [] as DistributionEntry[];
    }

    const preferredOrder = ["0-40", "40-60", "60-80", "80-90", "90-100"];
    const entries = Object.entries(distribution).map(([name, value]) => ({
      name,
      value: Number(value) || 0
    }));
    entries.sort((a, b) => {
      const aIndex = preferredOrder.indexOf(a.name);
      const bIndex = preferredOrder.indexOf(b.name);
      if (aIndex === -1 && bIndex === -1) {
        return a.name.localeCompare(b.name);
      }
      if (aIndex === -1) {
        return 1;
      }
      if (bIndex === -1) {
        return -1;
      }
      return aIndex - bIndex;
    });
    return entries;
  }, [taxonomyResults?.confidence_distribution]);

  const topPredictions = useMemo(
    () => (taxonomyResults?.top_predictions ?? []).slice(0, 20),
    [taxonomyResults?.top_predictions]
  );

  const totalPhylumCount = useMemo(
    () => phylumData.reduce((sum, row) => sum + row.value, 0),
    [phylumData]
  );

  const totalGenusCount = useMemo(
    () => genusData.reduce((sum, row) => sum + row.value, 0),
    [genusData]
  );

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
          <div><strong>Current step:</strong> {run.current_step ? run.current_step.replace(/_/g, " ") : "--"}</div>
          <div><strong>Live status:</strong> {run.current_message ?? "--"}</div>
          <div><strong>Progress:</strong> {typeof run.progress === "number" ? `${Math.max(0, Math.min(100, run.progress)).toFixed(0)}%` : "--"}</div>
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
                  : step.status === "running"
                  ? ((step.results as { message?: string })?.message ?? "Processing in progress")
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

      <section className="card" style={{ display: "grid", gap: "18px" }}>
        <div className="section-title">
          <h3>Classification intelligence</h3>
          <span>Detailed taxonomy and confidence diagnostics</span>
        </div>
        {!taxonomyResults ? (
          <div className="empty-state">Taxonomic classification results are not available yet for this run.</div>
        ) : (
          <>
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-card__label">Classifier</div>
                <div className="stat-card__value" style={{ fontSize: "22px" }}>
                  {taxonomyResults.classifier ?? "--"}
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-card__label">Classification mode</div>
                <div className="stat-card__value" style={{ fontSize: "22px" }}>
                  {taxonomyResults.classification_mode ?? "--"}
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-card__label">Classified sequences</div>
                <div className="stat-card__value" style={{ fontSize: "22px" }}>
                  {(taxonomyResults.total_classified ?? 0).toLocaleString()}
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-card__label">Mean confidence</div>
                <div className="stat-card__value" style={{ fontSize: "22px" }}>
                  {typeof taxonomyResults.mean_confidence === "number"
                    ? `${taxonomyResults.mean_confidence.toFixed(2)}%`
                    : "--"}
                </div>
              </div>
            </div>

            <div
              className="page-grid"
              style={{
                gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
                gap: "16px"
              }}
            >
              <div className="card" style={{ padding: "18px", display: "grid", gap: "10px" }}>
                <div className="section-title">
                  <h3>Phylum composition</h3>
                  <span>Top 10 groups</span>
                </div>
                {phylumData.length === 0 ? (
                  <div className="empty-state">No phylum composition data available.</div>
                ) : (
                  <>
                    <div style={{ width: "100%", height: "260px" }}>
                      <ResponsiveContainer>
                        <PieChart>
                          <Pie
                            data={phylumData}
                            dataKey="value"
                            nameKey="name"
                            innerRadius={58}
                            outerRadius={98}
                            paddingAngle={2}
                          >
                            {phylumData.map((entry, index) => (
                              <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip
                            formatter={(value: number) => [
                              `${value.toLocaleString()} (${formatPct(value, totalPhylumCount)})`,
                              "Sequences"
                            ]}
                            contentStyle={{
                              background: "rgba(11, 19, 36, 0.96)",
                              border: "1px solid rgba(255,255,255,0.12)",
                              borderRadius: "10px",
                              color: "#f5f7fb"
                            }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                    <div style={{ display: "grid", gap: "6px" }}>
                      {phylumData.slice(0, 6).map((row, index) => (
                        <div
                          key={row.name}
                          style={{ display: "flex", justifyContent: "space-between", fontSize: "13px" }}
                        >
                          <span style={{ color: "var(--text-secondary)" }}>
                            <span
                              style={{
                                display: "inline-block",
                                width: "10px",
                                height: "10px",
                                borderRadius: "999px",
                                marginRight: "8px",
                                background: CHART_COLORS[index % CHART_COLORS.length]
                              }}
                            />
                            {row.name}
                          </span>
                          <span>{row.value.toLocaleString()}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <div className="card" style={{ padding: "18px", display: "grid", gap: "10px" }}>
                <div className="section-title">
                  <h3>Top genera</h3>
                  <span>Ranked by support</span>
                </div>
                {genusData.length === 0 ? (
                  <div className="empty-state">No genus distribution data available.</div>
                ) : (
                  <div style={{ width: "100%", height: "320px" }}>
                    <ResponsiveContainer>
                      <BarChart data={genusData} layout="vertical" margin={{ left: 8, right: 8, top: 8, bottom: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                        <XAxis type="number" stroke="var(--text-muted)" />
                        <YAxis
                          type="category"
                          dataKey="name"
                          width={100}
                          tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
                        />
                        <Tooltip
                          formatter={(value: number) => [
                            `${value.toLocaleString()} (${formatPct(value, totalGenusCount)})`,
                            "Sequences"
                          ]}
                          contentStyle={{
                            background: "rgba(11, 19, 36, 0.96)",
                            border: "1px solid rgba(255,255,255,0.12)",
                            borderRadius: "10px",
                            color: "#f5f7fb"
                          }}
                        />
                        <Bar dataKey="value" fill="#2be38b" radius={[0, 6, 6, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>

              <div className="card" style={{ padding: "18px", display: "grid", gap: "10px" }}>
                <div className="section-title">
                  <h3>Confidence profile</h3>
                  <span>Bucketed confidence counts</span>
                </div>
                {confidenceData.length === 0 ? (
                  <div className="empty-state">No confidence distribution data available.</div>
                ) : (
                  <div style={{ width: "100%", height: "260px" }}>
                    <ResponsiveContainer>
                      <BarChart data={confidenceData} margin={{ left: 6, right: 12, top: 6, bottom: 6 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                        <XAxis dataKey="name" stroke="var(--text-muted)" />
                        <YAxis stroke="var(--text-muted)" />
                        <Tooltip
                          formatter={(value: number) => [`${value.toLocaleString()} sequences`, "Count"]}
                          contentStyle={{
                            background: "rgba(11, 19, 36, 0.96)",
                            border: "1px solid rgba(255,255,255,0.12)",
                            borderRadius: "10px",
                            color: "#f5f7fb"
                          }}
                        />
                        <Bar dataKey="value" fill="#1ca769" radius={[6, 6, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            </div>

            <div className="card" style={{ padding: "18px", display: "grid", gap: "12px" }}>
              <div className="section-title">
                <h3>Per-sequence prediction preview</h3>
                <span>Top 20 predictions from latest classification</span>
              </div>
              {topPredictions.length === 0 ? (
                <div className="empty-state">No per-sequence predictions were returned by the classifier.</div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table className="table" style={{ minWidth: "920px" }}>
                    <thead>
                      <tr>
                        <th>Sequence ID</th>
                        <th>Kingdom</th>
                        <th>Phylum / Cluster</th>
                        <th>Genus</th>
                        <th>Species</th>
                        <th>Confidence</th>
                        <th>Method</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topPredictions.map((prediction, index) => (
                        <tr key={`${prediction.sequence_id ?? "sequence"}-${index}`}>
                          <td>{prediction.sequence_id ?? "--"}</td>
                          <td>{prediction.kingdom ?? "Unknown"}</td>
                          <td>{prediction.phylum ?? "Unknown"}</td>
                          <td>{prediction.genus ?? "Unknown"}</td>
                          <td>{prediction.species ?? "Unknown"}</td>
                          <td>
                            {typeof prediction.confidence === "number"
                              ? `${prediction.confidence.toFixed(2)}%`
                              : "--"}
                          </td>
                          <td>{prediction.method ?? "--"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
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
