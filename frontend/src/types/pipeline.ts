export type PipelineStepKey =
  | "embedding_generation"
  | "preprocessing"
  | "feature_extraction"
  | "taxonomic_classification"
  | "abundance_quantification"
  | "report_generation";

export interface PipelineStep<T = Record<string, unknown>> {
  step: PipelineStepKey | string;
  status: "pending" | "running" | "completed" | "failed";
  results: T;
  startedAt?: string;
  finishedAt?: string;
}

export interface PipelineRun {
  sample_id: string;
  input_type: "single" | "paired" | string;
  input_files: string | string[];
  output_dir: string;
  start_time: string;
  end_time?: string;
  processing_time?: number;
  success: boolean;
  error?: string;
  status?: "queued" | "running" | "completed" | "failed" | string;
  current_step?: string;
  current_message?: string;
  progress?: number;
  pipeline_steps: PipelineStep[];
}

export interface TaxonomySummary {
  mean_confidence: number;
  phylum_distribution: Record<string, number>;
  genus_distribution?: Record<string, number>;
  species_distribution?: Record<string, number>;
  confidence_distribution?: Record<string, number>;
  classification_method?: string;
  classification_mode?: string;
  classifier?: string;
  total_classified: number;
  summary_file?: string;
  detailed_file?: string;
  predictions_file?: string;
}

export interface AbundanceSummary {
  total_reads: number;
  total_asvs: number;
  diversity_metrics: Record<string, Record<string, number>>;
  taxonomic_summary: Record<string, Record<string, number>>;
  abundance_file?: string;
  normalized_file?: string;
  diversity_file?: string;
}

export interface BatchRun {
  batch_id: string;
  total_samples: number;
  successful_samples: number;
  failed_samples: number;
  start_time: string;
  end_time?: string;
  total_processing_time?: number;
  status?: "queued" | "running" | "completed" | "failed" | string;
  error?: string;
  summary_report?: {
    summary_file?: string;
    total_asvs?: number;
    average_processing_time?: number;
    success_rate?: number;
  };
  sample_results: Record<string, PipelineRun>;
}

export interface DatabaseInfo {
  name: string;
  description: string;
  use_case: string;
  priority: "low" | "medium" | "high" | "critical" | string;
  status?: DatabaseStatus;
}

export interface DatabaseStatus {
  downloaded: number;
  total: number;
  status: "pending" | "running" | "partial" | "complete" | string;
  last_updated?: number;
}

export interface ApiError {
  message: string;
  details?: string;
}

export interface RunRequestPayload {
  sampleId: string;
  inputType: "single" | "paired";
  files: string[];
  configOverrides?: Record<string, unknown>;
}

export interface BatchRequestPayload {
  runs: RunRequestPayload[];
  outputDir?: string;
}

export interface DashboardSnapshot {
  totalRuns: number;
  successRate: number;
  avgDuration: number;
  activeJobs: number;
  queueDepth: number;
  lastRunAt?: string;
}

export interface RunFileUploadResponse {
  file_name: string;
  stored_name: string;
  file_path: string;
  relative_path?: string;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
}

export interface LogResponse {
  entries: LogEntry[];
  download_path?: string;
}
