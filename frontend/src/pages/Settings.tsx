import { useEffect, useState } from "react";
import { FiSave } from "react-icons/fi";

interface SettingsState {
  defaultOutputDir: string;
  defaultInputType: "single" | "paired";
  modelName: string;
  maxLength: number;
  batchSize: number;
  device: "auto" | "cpu" | "cuda";
  runPollIntervalMs: number;
}

export const SETTINGS_STORAGE_KEY = "edna-app-settings";

const defaultSettings: SettingsState = {
  defaultOutputDir: "results",
  defaultInputType: "single",
  modelName: "zhihan1996/DNABERT-2-117M",
  maxLength: 256,
  batchSize: 16,
  device: "auto",
  runPollIntervalMs: 2000
};

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
          <h3>Embeddings run defaults</h3>
          <span>Defaults used by Single Run and Batch Run launch forms</span>
        </div>
        <div className="page-grid" style={{ gap: "16px" }}>
          <div className="card" style={{ padding: "18px", display: "grid", gap: "12px" }}>
            <div style={{ fontWeight: 600 }}>Run configuration</div>
            <div className="form-control">
              <label htmlFor="output-dir">Output directory</label>
              <input
                id="output-dir"
                value={settings.defaultOutputDir}
                onChange={(event) => handleInput("defaultOutputDir", event.target.value)}
              />
            </div>
            <div className="form-control">
              <label htmlFor="default-input-type">Default input type</label>
              <select
                id="default-input-type"
                value={settings.defaultInputType}
                onChange={(event) => handleInput("defaultInputType", event.target.value as SettingsState["defaultInputType"])}
              >
                <option value="single">Single-end</option>
                <option value="paired">Paired-end</option>
              </select>
            </div>
            <div className="form-control">
              <label htmlFor="model-name">Model name</label>
              <input
                id="model-name"
                value={settings.modelName}
                onChange={(event) => handleInput("modelName", event.target.value)}
              />
            </div>
            <div className="form-control">
              <label htmlFor="max-length">Max token length</label>
              <input
                id="max-length"
                type="number"
                value={settings.maxLength}
                onChange={(event) => handleInput("maxLength", Number(event.target.value))}
                min={32}
                max={2048}
              />
            </div>
            <div className="form-control">
              <label htmlFor="batch-size">Batch size</label>
              <input
                id="batch-size"
                type="number"
                value={settings.batchSize}
                onChange={(event) => handleInput("batchSize", Number(event.target.value))}
                min={1}
                max={512}
              />
            </div>
            <div className="form-control">
              <label htmlFor="device">Preferred device</label>
              <select
                id="device"
                value={settings.device}
                onChange={(event) => handleInput("device", event.target.value as SettingsState["device"])}
              >
                <option value="auto">Auto-detect</option>
                <option value="cpu">CPU</option>
                <option value="cuda">CUDA</option>
              </select>
            </div>
            <div className="form-control">
              <label htmlFor="poll-interval">Run poll interval (ms)</label>
              <input
                id="poll-interval"
                type="number"
                value={settings.runPollIntervalMs}
                onChange={(event) => handleInput("runPollIntervalMs", Number(event.target.value))}
                min={500}
                max={10000}
                step={100}
              />
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <button type="button" className="primary-button" onClick={handleSave}>
            <FiSave /> Save preferences
          </button>
          {saved ? <span style={{ color: "var(--accent)" }}>Settings saved</span> : null}
        </div>
      </section>
    </div>
  );
};

export default Settings;
