import { useMemo } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar
} from "recharts";
import api from "../services/api";
import { useAsyncData } from "../hooks/useAsyncData";
import StatCard from "../components/StatCard";
import type { PipelineRun } from "../types/pipeline";

const Dashboard = () => {
  const { data: snapshot, loading: loadingSnapshot } = useAsyncData(api.fetchDashboardSnapshot, [], {
    pollIntervalMs: 2000
  });
  const { data: recentRuns, loading: loadingRuns } = useAsyncData(api.fetchRecentRuns, [], {
    pollIntervalMs: 2000
  });

  const runChartData = useMemo(() => {
    if (!recentRuns) {
      return [];
    }
    return recentRuns
      .filter((run) => (run.status ?? (run.success ? "completed" : "failed")) === "completed")
      .slice(0, 8)
      .map((run) => ({
        name: run.sample_id,
        duration: run.processing_time ?? 0
      }));
  }, [recentRuns]);

  const phylumData = useMemo(() => {
    if (!recentRuns || recentRuns.length === 0) {
      return [];
    }
    const latestClassification = recentRuns[0].pipeline_steps.find((step) => step.step === "taxonomic_classification");
    const distribution = (latestClassification?.results as { phylum_distribution?: Record<string, number> })?.phylum_distribution;
    if (!distribution) {
      return [];
    }
    return Object.entries(distribution).map(([name, value]) => ({ name, value }));
  }, [recentRuns]);

  return (
    <div className="page-grid" style={{ gap: "32px" }}>
      <section className="stats-grid">
        <StatCard
          label="Total runs"
          value={snapshot ? snapshot.totalRuns.toString() : loadingSnapshot ? "..." : "0"}
          helper="Across all eDNA campaigns"
        />
        <StatCard
          label="Success rate"
          value={snapshot ? `${Math.round(snapshot.successRate * 100)}%` : loadingSnapshot ? "..." : "0%"}
          helper="Successful completions over total"
        />
        <StatCard
          label="Average duration"
          value={snapshot ? `${Math.round(snapshot.avgDuration)} s` : loadingSnapshot ? "..." : "--"}
          helper="From ingestion to reporting"
        />
        <StatCard
          label="Active jobs"
          value={snapshot ? snapshot.activeJobs.toString() : loadingSnapshot ? "..." : "0"}
          helper={`Queue depth ${snapshot ? snapshot.queueDepth : "--"}`}
        />
      </section>

      <section className="card" style={{ display: "grid", gap: "20px" }}>
        <div className="section-title">
          <h3>Processing velocity</h3>
          <span>Recent pipeline execution times</span>
        </div>
        <div style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={runChartData}>
              <defs>
                <linearGradient id="colorDuration" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.6} />
                  <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="name" stroke="var(--text-muted)" tickLine={false} axisLine={false} />
              <YAxis stroke="var(--text-muted)" tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{
                  background: "rgba(17, 28, 51, 0.92)",
                  border: "1px solid rgba(43, 227, 139, 0.25)",
                  borderRadius: "12px",
                  color: "var(--text-primary)"
                }}
              />
              <Area type="monotone" dataKey="duration" stroke="var(--accent)" fillOpacity={1} fill="url(#colorDuration)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="card" style={{ display: "grid", gap: "20px" }}>
        <div className="section-title">
          <h3>Dominant phyla snapshot</h3>
          <span>Distribution from most recent run</span>
        </div>
        <div style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={phylumData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" />
              <XAxis dataKey="name" stroke="var(--text-muted)" tickLine={false} axisLine={false} />
              <YAxis stroke="var(--text-muted)" tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{
                  background: "rgba(17, 28, 51, 0.92)",
                  border: "1px solid rgba(43, 227, 139, 0.25)",
                  borderRadius: "12px",
                  color: "var(--text-primary)"
                }}
              />
              <Bar dataKey="value" fill="var(--accent)" radius={[12, 12, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="card" style={{ display: "grid", gap: "12px" }}>
        <div className="section-title">
          <h3>Recent pipeline runs</h3>
          <span>{loadingRuns ? "Loading activity" : "Latest insights from mock data layer"}</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Sample</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Classified</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {(recentRuns ?? []).map((run: PipelineRun) => {
                const taxStep = run.pipeline_steps.find((step) => step.step === "taxonomic_classification");
                const classification = taxStep?.results as {
                  total_classified?: number;
                  mean_confidence?: number;
                } | undefined;
                const statusState = (run.status ?? (run.success ? "completed" : "failed")).toLowerCase();
                const statusLabel =
                  statusState === "completed"
                    ? "Completed"
                    : statusState === "running"
                    ? "Running"
                    : statusState === "queued"
                    ? "Queued"
                    : statusState === "pending"
                    ? "Pending"
                    : "Failed";
                const statusClass =
                  statusState === "completed"
                    ? "status-pill status-pill--success"
                    : statusState === "running" || statusState === "queued" || statusState === "pending"
                    ? "status-pill status-pill--pending"
                    : "status-pill status-pill--error";
                return (
                  <tr key={run.sample_id}>
                    <td>{run.sample_id}</td>
                    <td>{run.input_type}</td>
                    <td>
                      <span className={statusClass}>{statusLabel}</span>
                    </td>
                    <td>{run.processing_time ? `${Math.round(run.processing_time / 60)} min` : "--"}</td>
                    <td>{classification?.total_classified ?? "--"}</td>
                    <td>{classification?.mean_confidence ? `${classification.mean_confidence.toFixed(1)}%` : "--"}</td>
                  </tr>
                );
              })}
              {!loadingRuns && (!recentRuns || recentRuns.length === 0) ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "28px", color: "var(--text-muted)" }}>
                    No pipeline activity yet. Launch a run to see telemetry.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};

export default Dashboard;
