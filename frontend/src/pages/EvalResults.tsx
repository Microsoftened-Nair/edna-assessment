import { useEffect, useState, useMemo } from "react";
import { getEvalDnabert2 } from "../services/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend
} from "recharts";
import StatCard from "../components/StatCard";

const EvalResults = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEvalDnabert2()
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to load evaluation data");
        setLoading(false);
      });
  }, []);

  const chartData = useMemo(() => {
    if (!data?.report) return [];
    const classes = Object.keys(data.report).filter(
      (key) => key !== "accuracy" && key !== "macro avg" && key !== "weighted avg"
    );
    
    return classes.map((cls) => {
      const metrics = data.report[cls];
      return {
        name: cls,
        f1Score: metrics["f1-score"] * 100,
        precision: metrics["precision"] * 100,
        recall: metrics["recall"] * 100,
        support: metrics["support"]
      };
    }).sort((a, b) => b.f1Score - a.f1Score);
  }, [data]);

  if (loading) {
    return <div className="page-container"><p>Loading evaluation results...</p></div>;
  }

  if (error) {
    return <div className="page-container"><div className="error-message">{error}</div></div>;
  }

  if (!data) return null;

  const { metrics } = data;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">DNABERT-2 Evaluation</h1>
        <p className="page-description">
          Evaluation of DNABERT-2 embeddings on 16S mock database
        </p>
      </div>

      <div className="stats-grid">
        <StatCard
          label="Accuracy"
          value={`${(metrics.accuracy * 100).toFixed(2)}%`}
        />
        <StatCard
          label="Macro F1"
          value={`${(metrics.macro_f1 * 100).toFixed(2)}%`}
        />
        <StatCard
          label="Weighted F1"
          value={`${(metrics.weighted_f1 * 100).toFixed(2)}%`}
        />
        <StatCard
          label="Sequences"
          value={metrics.n_sequences_total_after_filter || metrics.n_sequences_total}
        />
      </div>

      <div className="results-card" style={{ marginTop: "2rem", padding: "1.5rem", background: "var(--color-surface)", borderRadius: "var(--radius-lg)", border: "1px solid var(--color-border)" }}>
        <h2 style={{ marginBottom: "1.5rem", fontSize: "1.125rem", fontWeight: 600 }}>Per-Class Metrics (Top and Bottom)</h2>
        <div style={{ height: "400px", width: "100%" }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{
                top: 20,
                right: 30,
                left: 20,
                bottom: 50,
              }}
            >
              <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
              <XAxis 
                dataKey="name" 
                angle={-45} 
                textAnchor="end" 
                height={80} 
                tick={{ fontSize: 12, fill: "var(--color-text-muted)" }} 
              />
              <YAxis 
                domain={[0, 100]} 
                tick={{ fontSize: 12, fill: "var(--color-text-muted)" }}
                tickFormatter={(val) => `${val}%`}
              />
              <RechartsTooltip 
                contentStyle={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", color: "var(--color-text)" }}
                formatter={(value: number, name: string) => [`${value.toFixed(1)}%`, name]}
              />
              <Legend wrapperStyle={{ paddingTop: "20px" }} />
              <Bar dataKey="f1Score" name="F1 Score" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="precision" name="Precision" fill="#10b981" radius={[4, 4, 0, 0]} />
              <Bar dataKey="recall" name="Recall" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default EvalResults;
