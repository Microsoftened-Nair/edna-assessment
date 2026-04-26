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

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api";
const AUTH_STORAGE_KEY = "edna_access_token";

const normalizeApiBaseUrl = (url: string): string =>
  url.replace(/:\/\/localhost(?=[:/]|$)/i, "://127.0.0.1");

const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_URL ?? DEFAULT_API_BASE_URL);
const API_AUTH_USERNAME = import.meta.env.VITE_API_USERNAME ?? "admin";
const API_AUTH_PASSWORD = import.meta.env.VITE_API_PASSWORD ?? "password123";

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
  headers: {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    Pragma: "no-cache",
    Expires: "0"
  }
});

let accessToken: string | null = null;
let loginInFlight: Promise<string | null> | null = null;

const authUrl = `${API_BASE_URL.replace(/\/$/, "")}/auth/login`;

const saveToken = (token: string | null) => {
  accessToken = token;
  if (typeof window === "undefined") {
    return;
  }

  if (token) {
    window.localStorage.setItem(AUTH_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  }
};

const loadStoredToken = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(AUTH_STORAGE_KEY);
};

const getAccessToken = async (): Promise<string | null> => {
  if (accessToken) {
    return accessToken;
  }

  accessToken = loadStoredToken();
  if (accessToken) {
    return accessToken;
  }

  if (!loginInFlight) {
    loginInFlight = (async () => {
      try {
        const response = await axios.post<{ access_token?: string }>(
          authUrl,
          { username: API_AUTH_USERNAME, password: API_AUTH_PASSWORD },
          { timeout: 10000 }
        );
        const token = response.data?.access_token ?? null;
        saveToken(token);
        return token;
      } catch {
        saveToken(null);
        return null;
      } finally {
        loginInFlight = null;
      }
    })();
  }

  return loginInFlight;
};

client.interceptors.request.use(async (config) => {
  if ((config.url ?? "").includes("/auth/login")) {
    return config;
  }

  const token = await getAccessToken();
  if (token) {
    if (config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error?.response?.status;
    const originalRequest = error?.config as (typeof error.config & { _retried?: boolean }) | undefined;
    const requestUrl = originalRequest?.url ?? "";

    if (status === 401 && originalRequest && !originalRequest._retried && !requestUrl.includes("/auth/login")) {
      originalRequest._retried = true;
      saveToken(null);
      const token = await getAccessToken();
      if (token) {
        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${token}`;
        }
        return client(originalRequest);
      }
    }

    return Promise.reject(error);
  }
);

const buildApiUrl = (path: string) => {
  const normalizedBase = API_BASE_URL.replace(/\/$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
};

const api = {
  async fetchDashboardSnapshot(): Promise<DashboardSnapshot> {
    const { data } = await client.get<DashboardSnapshot>(`/dashboard?_t=${Date.now()}`);
    return data;
  },

  async fetchRecentRuns(): Promise<PipelineRun[]> {
    const { data } = await client.get<PipelineRun[]>(`/runs/recent?_t=${Date.now()}`);
    return data;
  },

  async fetchRunDetails(runId: string): Promise<PipelineRun> {
    const { data } = await client.get<PipelineRun>(`/runs/${runId}?_t=${Date.now()}`);
    return data;
  },

  async fetchActiveRun(): Promise<PipelineRun | null> {
    try {
      const { data } = await client.get<PipelineRun>(`/runs/active?_t=${Date.now()}`);
      return data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return null;
      }
      throw error;
    }
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

export const getEvalDnabert2 = async (): Promise<any> => {
  const { data } = await client.get<any>("/eval/dnabert2");
  return data;
};
