import { Link, useParams } from "react-router-dom";
import { FiClock, FiFileText } from "react-icons/fi";
import api from "../services/api";
import { useAsyncData } from "../hooks/useAsyncData";
import type { BatchRun } from "../types/pipeline";

const BatchDetails = () => {
  const { batchId } = useParams<{ batchId: string }>();
  const { data: batch, loading, error } = useAsyncData<BatchRun>(
    () => api.fetchBatchDetails(batchId ?? ""),
    [batchId],
    { immediate: Boolean(batchId) }
  );

  if (!batchId) {
    return <div className="empty-state">Select a batch from the results page to inspect.</div>;
  }

  if (loading) {
    return <div className="empty-state">Loading batch summary...</div>;
  }

  if (error || !batch) {
    return <div className="empty-state">Unable to load batch data.</div>;
  }

  const resolveStatus = (status?: string, success?: boolean) => {
    const state = (status ?? (success ? "completed" : "failed")).toLowerCase();
    if (state === "completed" || state === "running" || state === "queued" || state === "pending") {
      return state;
    }
    return "failed";
  };

  const formatStatusLabel = (state: string) => state.charAt(0).toUpperCase() + state.slice(1);

  const renderStatusPill = (state: string) => {
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
  };

  return (
    <div className="page-grid" style={{ gap: "24px" }}>
      <section className="card" style={{ display: "grid", gap: "16px" }}>
        <div className="section-title">
          <h3>Batch overview</h3>
          <span>{batch.batch_id}</span>
        </div>
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-card__label">Samples</div>
            <div className="stat-card__value">{batch.total_samples}</div>
          </div>
          <div className="stat-card">
            <div className="stat-card__label">Success</div>
            <div className="stat-card__value">
              {batch.successful_samples}/{batch.total_samples}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-card__label">Processing time</div>
            <div className="stat-card__value">{Math.round((batch.total_processing_time ?? 0) / 60)} min</div>
          </div>
          <div className="stat-card">
            <div className="stat-card__label">Success rate</div>
            <div className="stat-card__value">
              {batch.summary_report?.success_rate
                ? `${Math.round(batch.summary_report.success_rate * 100)}%`
                : "--"}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-card__label">Status</div>
            <div className="stat-card__value">
              {formatStatusLabel(resolveStatus(batch.status, batch.successful_samples === batch.total_samples))}
            </div>
          </div>
        </div>
        {batch.error ? <div style={{ color: "#ff7b89", fontSize: "13px" }}>{batch.error}</div> : null}
      </section>

      <section className="card" style={{ display: "grid", gap: "16px" }}>
        <div className="section-title">
          <h3>Sample statuses</h3>
          <span>All runs included in this batch</span>
        </div>
        <div className="page-grid" style={{ gap: "16px" }}>
          {Object.entries(batch.sample_results).map(([sampleId, run]) => (
            <div key={sampleId} className="card card--interactive" style={{ padding: "18px", display: "grid", gap: "12px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{sampleId}</div>
                  <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                    {run.input_type} • {formatStatusLabel(resolveStatus(run.status, run.success))}
                  </div>
                </div>
                {renderStatusPill(resolveStatus(run.status, run.success))}
              </div>
              <div style={{ display: "flex", gap: "12px", alignItems: "center", fontSize: "13px", color: "var(--text-muted)" }}>
                <FiClock /> Duration {run.processing_time ? `${Math.round(run.processing_time / 60)} min` : "--"}
              </div>
              {run.error ? (
                <div style={{ fontSize: "13px", color: "#ff7b89" }}>{run.error}</div>
              ) : null}
              <Link to={`/results/${sampleId}`} className="secondary-button">
                <FiFileText /> View run details
              </Link>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default BatchDetails;
