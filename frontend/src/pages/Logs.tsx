import { useMemo } from "react";
import { FiDownload, FiLogOut, FiTerminal } from "react-icons/fi";
import api from "../services/api";
import { useAsyncData } from "../hooks/useAsyncData";
import type { LogEntry } from "../types/pipeline";

const levelClass = (level: string) => {
  switch (level) {
    case "ERROR":
      return "status-pill status-pill--error";
    case "WARN":
      return "status-pill status-pill--pending";
    default:
      return "status-pill";
  }
};

const Logs = () => {
  const { data: payload, loading, error, refresh } = useAsyncData(api.fetchLogs, []);

  const entries = payload?.entries ?? [];

  const readableLogs = useMemo(() => {
    const toLocal = (value: string) => {
      const isoCandidate = value.replace(" ", "T").replace(",", ".");
      const maybeIso = isoCandidate.endsWith("Z") ? isoCandidate : `${isoCandidate}Z`;
      const localDate = new Date(maybeIso);
      if (Number.isNaN(localDate.getTime())) {
        return value;
      }
      return localDate.toLocaleString();
    };

    return entries.map((entry: LogEntry) => ({
      ...entry,
      localTime: toLocal(entry.timestamp)
    }));
  }, [entries]);

  const handleExport = () => {
    if (!payload?.download_path) {
      return;
    }
    api.openFile(payload.download_path, { mode: "attachment" });
  };

  return (
    <div className="page-grid" style={{ gap: "24px" }}>
      <section className="card" style={{ display: "grid", gap: "16px" }}>
        <div className="section-title">
          <h3>Pipeline logs</h3>
          <span>Captured from `data/api/logs/api.log`</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            <FiTerminal />
            <span style={{ color: "var(--text-muted)", fontSize: "13px" }}>
              {loading ? "Loading latest events..." : `Showing ${entries.length} records`}
            </span>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button type="button" className="secondary-button" onClick={() => { void refresh(); }} disabled={loading}>
              Refresh
            </button>
            <button type="button" className="secondary-button" onClick={handleExport} disabled={!payload?.download_path}>
              <FiDownload />
              Export log
            </button>
          </div>
        </div>
        {error ? (
          <div style={{ color: "#ff7b89", fontSize: "13px" }}>
            Unable to load new log entries. {error.message}
          </div>
        ) : null}
        <div className="card" style={{ maxHeight: "420px", overflowY: "auto", padding: "18px", display: "grid", gap: "12px" }}>
          {readableLogs.length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
              {loading ? "Fetching log entries..." : "No log lines recorded yet."}
            </div>
          ) : (
            readableLogs.map((entry) => (
              <div key={`${entry.timestamp}-${entry.message}`} style={{ display: "grid", gap: "4px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontFamily: "monospace", fontSize: "13px", color: "var(--text-muted)" }}>{entry.localTime}</span>
                  <span className={levelClass(entry.level)}>{entry.level}</span>
                </div>
                <div style={{ fontFamily: "monospace", fontSize: "13px", lineHeight: 1.6 }}>{entry.message}</div>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="card" style={{ display: "grid", gap: "12px" }}>
        <div className="section-title">
          <h3>Streaming integration</h3>
          <span>Attach the live feed to an external observability stack</span>
        </div>
        <div style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
          Configure the backend to publish pipeline events to Kafka, WebSockets, or OpenTelemetry collector.
          The frontend is ready to subscribe once `enableStreaming` is set in Settings.
        </div>
        <button type="button" className="primary-button" disabled title="Realtime monitoring will be enabled in a future update">
          <FiLogOut />
          Connect to Grafana Live
        </button>
      </section>
    </div>
  );
};

export default Logs;
