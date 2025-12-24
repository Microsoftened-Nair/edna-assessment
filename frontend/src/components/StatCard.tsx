interface StatCardProps {
  label: string;
  value: string;
  helper?: string;
  trend?: {
    value: string;
    direction: "up" | "down" | "flat";
  };
}

const StatCard = ({ label, value, helper, trend }: StatCardProps) => {
  return (
    <div className="card card--interactive stat-card">
      <div className="stat-card__label">{label}</div>
      <div className="stat-card__value">{value}</div>
      {trend ? (
        <div className="stat-card__trend">
          <span>{trend.direction === "down" ? "v" : trend.direction === "flat" ? "-" : "^"}</span>
          {trend.value}
        </div>
      ) : null}
      {helper ? <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>{helper}</div> : null}
    </div>
  );
};

export default StatCard;
