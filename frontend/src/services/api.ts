import axios from "axios";
import type {
  DashboardSnapshot,
  PipelineRun,
  BatchRun,
  DatabaseInfo,
  RunRequestPayload,
  BatchRequestPayload,
  RunFileUploadResponse,
  LogResponse
} from "../types/pipeline";

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000
});

const buildApiUrl = (path: string) => {
  const normalizedBase = API_BASE_URL.replace(/\/$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
};

const api = {
  async fetchDashboardSnapshot(): Promise<DashboardSnapshot> {
    const { data } = await client.get<DashboardSnapshot>("/dashboard");
    return data;
  },

  async fetchRecentRuns(): Promise<PipelineRun[]> {
    const { data } = await client.get<PipelineRun[]>("/runs/recent");
    return data;
  },

  async fetchRunDetails(runId: string): Promise<PipelineRun> {
    const { data } = await client.get<PipelineRun>(`/runs/${runId}`);
    return data;
  },

  async triggerRun(payload: RunRequestPayload): Promise<PipelineRun> {
    const { data } = await client.post<PipelineRun>("/runs", payload);
    return data;
  },

  async triggerBatchRun(payload: BatchRequestPayload): Promise<BatchRun> {
    const { data } = await client.post<BatchRun>("/runs/batch", payload);
    return data;
  },

  async fetchBatchDetails(batchId: string): Promise<BatchRun> {
    const { data } = await client.get<BatchRun>(`/runs/batch/${batchId}`);
    return data;
  },

  async uploadRunFile(file: File): Promise<RunFileUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const { data } = await client.post<RunFileUploadResponse>("/uploads", formData, {
      headers: {
        "Content-Type": "multipart/form-data"
      }
    });

    return data;
  },

  async fetchDatabases(): Promise<DatabaseInfo[]> {
    const { data } = await client.get<DatabaseInfo[]>("/databases");
    return data;
  },

  async requestDatabaseDownload(name: string): Promise<DatabaseInfo> {
    const { data } = await client.post<DatabaseInfo>(`/databases/${name}/download`);
    return data;
  },

  async cancelDatabaseDownload(name: string): Promise<void> {
    await client.post(`/databases/${name}/cancel`);
  },

  async fetchLogs(): Promise<LogResponse> {
    const { data } = await client.get<LogResponse>("/logs");
    return data;
  },

  buildFileUrl(filePath: string, options: { mode?: "inline" | "attachment"; downloadName?: string } = {}): string {
    const params = new URLSearchParams();
    params.set("path", filePath);
    params.set("mode", options.mode ?? "attachment");
    if (options.downloadName) {
      params.set("name", options.downloadName);
    }
    return `${buildApiUrl("/files")}?${params.toString()}`;
  },

  openFile(filePath: string, options: { mode?: "inline" | "attachment"; downloadName?: string } = {}): void {
    const url = this.buildFileUrl(filePath, options);
    window.open(url, "_blank", "noopener");
  }
};

export default api;
