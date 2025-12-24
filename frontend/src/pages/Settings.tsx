import { useEffect, useState } from "react";
import { FiSave, FiToggleLeft, FiToggleRight } from "react-icons/fi";

interface SettingsState {
  autoSyncDatabases: boolean;
  enableStreaming: boolean;
  gpuAcceleration: boolean;
  defaultOutputDir: string;
  maxConcurrentJobs: number;
  enableCodexPreview: boolean;
}

const defaultSettings: SettingsState = {
  autoSyncDatabases: true,
  enableStreaming: false,
  gpuAcceleration: true,
  defaultOutputDir: "results",
  maxConcurrentJobs: 4,
  enableCodexPreview: true
};

const SETTINGS_STORAGE_KEY = "edna-app-settings";

const Settings = () => {
  const [settings, setSettings] = useState<SettingsState>(defaultSettings);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      const stored = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as Partial<SettingsState>;
        setSettings((state) => ({ ...state, ...parsed }));
      }
    } catch {
      // Ignore malformed storage entries
    }
  }, []);

  const handleToggle = (key: keyof SettingsState) => {
    setSaved(false);
    setSettings((state: SettingsState) => ({
      ...state,
      [key]: typeof state[key] === "boolean" ? !state[key] : state[key]
    }));
  };

  const handleInput = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
    setSaved(false);
    setSettings((state: SettingsState) => ({ ...state, [key]: value }));
  };

  const handleSave = () => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    }
    setSaved(true);
  };

  return (
    <div className="page-grid" style={{ gap: "24px", maxWidth: "900px" }}>
      <section className="card" style={{ display: "grid", gap: "18px" }}>
        <div className="section-title">
          <h3>Operational preferences</h3>
          <span>Adjust pipeline defaults and infrastructure options</span>
        </div>
        <div className="page-grid" style={{ gap: "16px" }}>
          <div className="card" style={{ padding: "18px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>Database auto-sync</div>
              <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
                Periodically refresh NCBI resources according to cron schedule.
              </div>
            </div>
            <button type="button" className="secondary-button" onClick={() => handleToggle("autoSyncDatabases")}
              aria-pressed={settings.autoSyncDatabases}
            >
              {settings.autoSyncDatabases ? <FiToggleRight size={22} /> : <FiToggleLeft size={22} />}
            </button>
          </div>

          <div className="card" style={{ padding: "18px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>Realtime telemetry</div>
              <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
                Stream pipeline events to the dashboard via WebSockets.
              </div>
            </div>
            <button type="button" className="secondary-button" onClick={() => handleToggle("enableStreaming")}
              aria-pressed={settings.enableStreaming}
            >
              {settings.enableStreaming ? <FiToggleRight size={22} /> : <FiToggleLeft size={22} />}
            </button>
          </div>

          <div className="card" style={{ padding: "18px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>GPU acceleration</div>
              <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
                Offload deep learning stages to CUDA-compatible devices.
              </div>
            </div>
            <button type="button" className="secondary-button" onClick={() => handleToggle("gpuAcceleration")}
              aria-pressed={settings.gpuAcceleration}
            >
              {settings.gpuAcceleration ? <FiToggleRight size={22} /> : <FiToggleLeft size={22} />}
            </button>
          </div>

          <div className="card" style={{ padding: "18px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 600 }}>GPT-5-Codex preview</div>
              <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
                Enable GPT-5-Codex (Preview) capabilities for all analyst clients.
              </div>
            </div>
            <button type="button" className="secondary-button" onClick={() => handleToggle("enableCodexPreview")}
              aria-pressed={settings.enableCodexPreview}
            >
              {settings.enableCodexPreview ? <FiToggleRight size={22} /> : <FiToggleLeft size={22} />}
            </button>
          </div>

          <div className="card" style={{ padding: "18px", display: "grid", gap: "12px" }}>
            <div style={{ fontWeight: 600 }}>Defaults</div>
            <div className="form-control">
              <label htmlFor="output-dir">Output directory</label>
              <input
                id="output-dir"
                value={settings.defaultOutputDir}
                onChange={(event) => handleInput("defaultOutputDir", event.target.value)}
              />
            </div>
            <div className="form-control">
              <label htmlFor="max-jobs">Max concurrent runs</label>
              <input
                id="max-jobs"
                type="number"
                value={settings.maxConcurrentJobs}
                onChange={(event) => handleInput("maxConcurrentJobs", Number(event.target.value))}
                min={1}
                max={32}
              />
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <button type="button" className="primary-button" onClick={handleSave}>
            <FiSave /> Save preferences
          </button>
          {saved ? <span style={{ color: "var(--accent)" }}>Settings updated (mock)</span> : null}
        </div>
      </section>
    </div>
  );
};

export default Settings;
