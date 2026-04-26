import { Link } from "react-router-dom";
import { FiArrowRightCircle, FiFolder } from "react-icons/fi";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from "recharts";
import api from "../services/api";
import { useAsyncData } from "../hooks/useAsyncData";
import type { PipelineRun } from "../types/pipeline";

const chartColors = ["#2be38b", "#4f9dde", "#c47bff", "#f9a23c", "#f45b69", "#27c7b8"];

const statusLabel = (run: PipelineRun): { label: string; pillClass: string } => {
  const state = (run.status ?? (run.success ? "completed" : "failed")).toLowerCase();
  if (state === "completed") {
    return { label: "Completed", pillClass: "status-pill status-pill--success" };
  }
  if (state === "running" || state === "queued") {
    return { label: state === "running" ? "Running" : "Queued", pillClass: "status-pill status-pill--pending" };
  }
  return { label: "Failed", pillClass: "status-pill status-pill--error" };
};

const Results = () => {
  const { data: runs, loading, error } = useAsyncData(api.fetchRecentRuns, [], {
    pollIntervalMs: 2000
  });

  return (
    <div className="page-grid" style={{ gap: "24px" }}>
      <section className="card" style={{ display: "grid", gap: "16px" }}>
        <div className="section-title">
          <h3>Pipeline outputs</h3>
          <span>Browse analyses, open HTML reports, and export summaries</span>
        </div>
        <div className="page-grid" style={{ gap: "18px" }}>
          {loading ? (
            <div className="empty-state">Loading recent runs...</div>
          ) : error ? (
            <div className="empty-state">Failed to load runs from API. Check backend connectivity/auth and refresh.</div>
          ) : runs && runs.length > 0 ? (
            runs.map((run: PipelineRun) => {
              const classification = run.pipeline_steps.find((step) => step.step === "taxonomic_classification");
              const abundance = run.pipeline_steps.find((step) => step.step === "abundance_quantification");
              const classifiedCount = (classification?.results as { total_classified?: number })?.total_classified;
              const confidence = (classification?.results as { mean_confidence?: number })?.mean_confidence;
              const totalReads = (abundance?.results as { total_reads?: number })?.total_reads;

              const phylumDistribution = (classification?.results as {
                phylum_distribution?: Record<string, number>;
              })?.phylum_distribution;

              const distributionData = (() => {
                if (!phylumDistribution) {
                  return [] as Array<{ name: string; value: number }>;
                }
                const entries = Object.entries(phylumDistribution).sort((a, b) => b[1] - a[1]);
                const top = entries.slice(0, 5).map(([name, value]) => ({ name, value }));
                const otherSum = entries.slice(5).reduce((acc, [, value]) => acc + value, 0);
                if (otherSum > 0) {
                  top.push({ name: "Other", value: otherSum });
                }
                return top;
              })();

              const distributionTotal = distributionData.reduce((acc, item) => acc + item.value, 0);

              const { label, pillClass } = statusLabel(run);
              const state = (run.status ?? (run.success ? "completed" : "failed")).toLowerCase();
              const description =
                state === "failed"
                  ? run.error ?? "Failed"
                  : state === "running"
                  ? "Running analysis"
                  : state === "queued"
                  ? "Queued for execution"
                  : "Completed successfully";

              const progress = Math.max(0, Math.min(100, run.progress ?? 0));
              const showLiveProgress = state === "running" || state === "queued" || state === "pending";
              return (
                <div key={run.sample_id} className="card card--interactive" style={{ display: "grid", gap: "12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                      <div className="sidebar__brand-icon" style={{ width: "34px", height: "34px", fontSize: "16px" }}>
                        <FiFolder />
                      </div>
                      <div>
                        <h3 style={{ margin: 0, fontSize: "17px" }}>{run.sample_id}</h3>
                        <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
                          {description}
                        </div>
                      </div>
                    </div>
                    <span className={pillClass}>{label}</span>
                  </div>

                  <div className="page-grid" style={{ gap: "12px", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
                    <div className="form-control">
                      <label>Duration</label>
                      <span>{run.processing_time ? `${Math.round(run.processing_time / 60)} min` : "--"}</span>
                    </div>
                    <div className="form-control">
                      <label>Classified</label>
                      <span>{classifiedCount ?? "--"}</span>
                    </div>
                    <div className="form-control">
                      <label>Confidence</label>
                      <span>{confidence ? `${confidence.toFixed(1)}%` : "--"}</span>
                    </div>
                    <div className="form-control">
                      <label>Total reads</label>
                      <span>{totalReads ? totalReads.toLocaleString() : "--"}</span>
                    </div>
                  </div>

                  {showLiveProgress ? (
                    <div style={{ display: "grid", gap: "8px" }}>
                      <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                        {run.current_message ?? "Processing..."}
                      </div>
                      <div style={{ height: "8px", width: "100%", borderRadius: "999px", background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                        <div
                          style={{
                            height: "100%",
                            width: `${progress}%`,
                            background: "linear-gradient(90deg, var(--accent), #43d29d)",
                            transition: "width 300ms ease"
                          }}
                        />
                      </div>
                      <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                        {progress.toFixed(0)}% complete{run.current_step ? ` • ${run.current_step.replace(/_/g, " ")}` : ""}
                      </div>
                    </div>
                  ) : null}

                  <div className="results-card__chart">
                    <div className="form-control" style={{ margin: 0 }}>
                      <label>Taxonomic distribution</label>
                      {distributionData.length > 0 && distributionTotal > 0 ? (
                        <ResponsiveContainer width="100%" height={180}>
                          <PieChart>
                            <Tooltip
                              formatter={(value: number, name: string) => [`${value}`, name]}
                              contentStyle={{
                                background: "rgba(17, 28, 51, 0.92)",
                                border: "1px solid rgba(43, 227, 139, 0.25)",
                                borderRadius: "12px",
                                color: "var(--text-primary)",
                                fontSize: "12px"
                              }}
                            />
                            <Pie
                              data={distributionData}
                              dataKey="value"
                              nameKey="name"
                              innerRadius={45}
                              outerRadius={70}
                              paddingAngle={3}
                            >
                              {distributionData.map((entry, index) => (
                                <Cell key={entry.name} fill={chartColors[index % chartColors.length]} />
                              ))}
                            </Pie>
                          </PieChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="results-card__chart-empty">Distribution data unavailable</div>
                      )}
                    </div>
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
                      Output directory: {run.output_dir}
                    </div>
                    <Link to={`/results/${run.sample_id}`} className="secondary-button">
                      View details
                      <FiArrowRightCircle />
                    </Link>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="empty-state">No runs yet. Launch your first sample to populate this view.</div>
          )}
        </div>
      </section>
    </div>
  );
};

export default Results;
