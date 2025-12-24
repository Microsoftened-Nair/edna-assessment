import type {
  DashboardSnapshot,
  PipelineRun,
  BatchRun,
  DatabaseInfo,
  RunRequestPayload,
  BatchRequestPayload,
  RunFileUploadResponse
} from "../types/pipeline";

const wait = (ms = 220) => new Promise((resolve) => setTimeout(resolve, ms));

const nowIso = () => new Date().toISOString();

const mockRuns: PipelineRun[] = [
  {
    sample_id: "abyssal_ridge_01",
    input_type: "paired",
    input_files: ["/demo/raw/abyssal_ridge_01_R1.fastq", "/demo/raw/abyssal_ridge_01_R2.fastq"],
    output_dir: "/demo/results/abyssal_ridge_01",
    start_time: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    end_time: new Date(Date.now() - 1000 * 60 * 35).toISOString(),
    processing_time: 600,
    success: true,
    status: "completed",
    pipeline_steps: [
      {
        step: "preprocessing",
        status: "completed",
        results: {
          final_asvs: 184,
          final_asv_file: "asv_sequences.fasta",
          quality_report: "quality_report.json"
        }
      },
      {
        step: "feature_extraction",
        status: "completed",
        results: {
          feature_types: ["kmer", "embeddings", "composition"],
          recommended_features: ["transformer_embeddings", "kmer_signature"]
        }
      },
      {
        step: "taxonomic_classification",
        status: "completed",
        results: {
          total_classified: 156,
          mean_confidence: 87.4,
          phylum_distribution: {
            Cnidaria: 42,
            Dinophyta: 31,
            Ciliophora: 24,
            "Unknown": 28
          }
        }
      },
      {
        step: "abundance_quantification",
        status: "completed",
        results: {
          total_reads: 425000,
          total_asvs: 184,
          diversity_metrics: {
            abyssal_ridge_01: {
              shannon: 3.45,
              simpson: 0.87,
              chao1: 234.5,
              pielou_evenness: 0.73
            }
          }
        }
      },
      {
        step: "report_generation",
        status: "completed",
        results: {
          report_file: "sample_report.html"
        }
      }
    ]
  },
  {
    sample_id: "hydrothermal_vent_12",
    input_type: "single",
    input_files: ["/demo/raw/hydrothermal_vent_12.fastq"],
    output_dir: "/demo/results/hydrothermal_vent_12",
    start_time: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
    end_time: new Date(Date.now() - 1000 * 60 * 110).toISOString(),
    processing_time: 600,
    success: true,
    status: "completed",
    pipeline_steps: [
      {
        step: "preprocessing",
        status: "completed",
        results: {
          final_asvs: 212,
          final_asv_file: "asv_sequences.fasta"
        }
      },
      {
        step: "feature_extraction",
        status: "completed",
        results: {
          feature_types: ["kmer", "embeddings", "composition"],
          recommended_features: ["transformer_embeddings"]
        }
      },
      {
        step: "taxonomic_classification",
        status: "completed",
        results: {
          total_classified: 198,
          mean_confidence: 81.2,
          phylum_distribution: {
            Arthropoda: 52,
            Annelida: 33,
            "Unknown": 14
          }
        }
      },
      {
        step: "abundance_quantification",
        status: "completed",
        results: {
          total_reads: 512000,
          total_asvs: 212,
          diversity_metrics: {
            hydrothermal_vent_12: {
              shannon: 3.92,
              simpson: 0.91,
              chao1: 260.1,
              pielou_evenness: 0.78
            }
          }
        }
      },
      {
        step: "report_generation",
        status: "completed",
        results: {
          report_file: "sample_report.html"
        }
      }
    ]
  }
];

const mockBatch: BatchRun = {
  batch_id: "deep_trench_survey",
  total_samples: 8,
  successful_samples: 7,
  failed_samples: 1,
  start_time: new Date(Date.now() - 1000 * 60 * 300).toISOString(),
  end_time: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
  total_processing_time: 10800,
  status: "completed",
  summary_report: {
    summary_file: "batch_summary.html",
    total_asvs: 1264,
    average_processing_time: 920,
    success_rate: 0.875
  },
  sample_results: Object.fromEntries(mockRuns.map((run) => [run.sample_id, run]))
};

const mockDatabases: DatabaseInfo[] = [
  {
    name: "taxdb",
    description: "NCBI taxonomy database (critical for mapping IDs)",
    use_case: "taxonomy_mapping",
    priority: "critical",
    status: {
      downloaded: 1,
      total: 1,
      status: "complete",
      last_updated: Date.now() / 1000 - 3600
    }
  },
  {
    name: "ITS_eukaryote_sequences",
    description: "ITS sequences for marine eukaryotes",
    use_case: "eukaryote_identification",
    priority: "high",
    status: {
      downloaded: 1,
      total: 1,
      status: "complete",
      last_updated: Date.now() / 1000 - 86400
    }
  },
  {
    name: "18S_fungal_sequences",
    description: "18S rRNA sequences for deep-sea fungi",
    use_case: "fungal_identification",
    priority: "high",
    status: {
      downloaded: 0,
      total: 1,
      status: "pending"
    }
  },
  {
    name: "core_nt",
    description: "Core nucleotide database subset",
    use_case: "balanced_analysis",
    priority: "medium",
    status: {
      downloaded: 3,
      total: 6,
      status: "partial"
    }
  }
];

export const mockApi = {
  async fetchDashboardSnapshot(): Promise<DashboardSnapshot> {
    await wait();
    const totalRuns = 42;
    const successful = 39;
    const avgDuration = 812;
    return {
      totalRuns,
      successRate: successful / totalRuns,
      avgDuration,
      activeJobs: 2,
      queueDepth: 4,
      lastRunAt: mockRuns[0]?.end_time
    };
  },

  async fetchRecentRuns(): Promise<PipelineRun[]> {
    await wait();
    return mockRuns;
  },

  async fetchRunDetails(runId: string): Promise<PipelineRun> {
    await wait();
    const run = mockRuns.find((item) => item.sample_id === runId);
    if (run) {
      return run;
    }
    return {
      sample_id: runId,
      input_type: "single",
      input_files: ["/demo/raw/" + runId + ".fastq"],
      output_dir: "/demo/results/" + runId,
      start_time: nowIso(),
      success: false,
      status: "failed",
      error: "Run not found",
      pipeline_steps: []
    };
  },

  async triggerRun(payload: RunRequestPayload): Promise<PipelineRun> {
    await wait(450);
    const newRun: PipelineRun = {
      sample_id: payload.sampleId,
      input_type: payload.inputType,
      input_files: payload.files,
      output_dir: `/demo/results/${payload.sampleId}`,
      start_time: nowIso(),
      success: false,
      status: "queued",
      pipeline_steps: []
    };
    mockRuns.unshift(newRun);
    return newRun;
  },

  async triggerBatchRun(payload: BatchRequestPayload): Promise<BatchRun> {
    await wait(650);
    return {
      ...mockBatch,
      batch_id: `batch_${Date.now()}`,
      total_samples: payload.runs.length,
      status: "queued",
      sample_results: {}
    };
  },

  async fetchBatchDetails(batchId: string): Promise<BatchRun> {
    await wait();
    return { ...mockBatch, batch_id: batchId };
  },

  async uploadRunFile(file: File): Promise<RunFileUploadResponse> {
    await wait(300);
    const filePath = `/mock/uploads/${Date.now()}_${file.name}`;
    return {
      file_name: file.name,
      stored_name: filePath,
      file_path: filePath,
      relative_path: filePath
    };
  },

  async fetchDatabases(): Promise<DatabaseInfo[]> {
    await wait();
    return mockDatabases;
  },

  async requestDatabaseDownload(name: string): Promise<DatabaseInfo> {
    await wait(500);
    const db = mockDatabases.find((item) => item.name === name);
    if (db) {
      db.status = {
        downloaded: db.status?.downloaded ?? 0,
        total: db.status?.total ?? 1,
        status: "running",
        last_updated: Date.now() / 1000
      };
      return db;
    }
    const newDb: DatabaseInfo = {
      name,
      description: "Custom database",
      use_case: "custom",
      priority: "medium",
      status: {
        downloaded: 0,
        total: 1,
        status: "running",
        last_updated: Date.now() / 1000
      }
    };
    mockDatabases.push(newDb);
    return newDb;
  },

  async cancelDatabaseDownload(name: string): Promise<void> {
    await wait(300);
    const db = mockDatabases.find((item) => item.name === name);
    if (db && db.status) {
      db.status.status = "pending";
    }
  }
};
