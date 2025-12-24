import { useState } from "react";
import { FiArrowDownCircle, FiDatabase, FiServer } from "react-icons/fi";
import api from "../services/api";
import { useAsyncData } from "../hooks/useAsyncData";
import type { DatabaseInfo } from "../types/pipeline";

const priorityChip = (priority: string) => {
  switch (priority) {
    case "critical":
      return "status-pill status-pill--error";
    case "high":
      return "status-pill status-pill--success";
    case "medium":
      return "status-pill";
    default:
      return "status-pill status-pill--pending";
  }
};

const Databases = () => {
  const { data: databases, loading, refresh, error } = useAsyncData(api.fetchDatabases, []);
  const [inProgress, setInProgress] = useState<Record<string, boolean>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleDownload = async (db: DatabaseInfo) => {
    setErrorMessage(null);
    setInProgress((state) => ({ ...state, [db.name]: true }));
    try {
      await api.requestDatabaseDownload(db.name);
      await refresh();
    } catch (downloadError) {
      const rawMessage = downloadError instanceof Error ? downloadError.message : "Failed to start download";
      const friendlyMessage =
        rawMessage === "download-already-running"
          ? "Download already running for this database."
          : rawMessage === "cannot-cancel-in-progress"
          ? "The current download cannot be cancelled while in progress."
          : rawMessage;
      setErrorMessage(friendlyMessage);
    } finally {
      setInProgress((state) => ({ ...state, [db.name]: false }));
    }
  };

  return (
    <div className="page-grid" style={{ gap: "24px" }}>
      <section className="card" style={{ display: "grid", gap: "16px" }}>
        <div className="section-title">
          <h3>Reference database catalog</h3>
          <span>Synchronize curated taxonomic resources for the pipeline</span>
        </div>
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-card__label">Tracked datasets</div>
            <div className="stat-card__value">{databases?.length ?? 0}</div>
            <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
              Managed via `DatabaseManager` orchestration
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-card__label">Auto-sync</div>
            <div className="stat-card__value">Enabled</div>
            <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
              Configure cron hooks in settings
            </div>
          </div>
        </div>
      </section>

      <section className="page-grid" style={{ gap: "18px" }}>
        {error || errorMessage ? (
          <div style={{ color: "#ff7b89", fontSize: "13px" }}>
            {error?.message ?? errorMessage}
          </div>
        ) : null}
        {loading ? (
          <div className="empty-state">Loading database metadata...</div>
        ) : (
          (databases ?? []).map((db) => (
            <div key={db.name} className="card card--interactive" style={{ display: "grid", gap: "12px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                  <div className="sidebar__brand-icon" style={{ width: "36px", height: "36px", fontSize: "16px" }}>
                    <FiDatabase />
                  </div>
                  <div>
                    <h3 style={{ margin: 0, fontSize: "17px" }}>{db.name}</h3>
                    <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>{db.description}</div>
                  </div>
                </div>
                <span className={priorityChip(db.priority)}>{db.priority}</span>
              </div>

              <div style={{ color: "var(--text-secondary)", fontSize: "14px" }}>{db.use_case}</div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", gap: "14px", alignItems: "center", color: "var(--text-muted)", fontSize: "13px" }}>
                  <FiServer />
                  {db.status?.status ?? "unknown"}
                  {typeof db.status?.downloaded === "number" && typeof db.status?.total === "number" ? (
                    <span>
                      {db.status.downloaded}/{db.status.total} files
                    </span>
                  ) : null}
                </div>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => handleDownload(db)}
                  disabled={inProgress[db.name]}
                >
                  <FiArrowDownCircle />
                  {inProgress[db.name] ? "Syncing" : "Download"}
                </button>
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  );
};

export default Databases;
