import { useEffect, useState } from "react";
import { FiBell, FiClock, FiMenu, FiRefreshCcw } from "react-icons/fi";

interface HeaderProps {
  title: string;
  breadcrumbPath: string;
  onToggleSidebar: () => void;
}

const formatBreadcrumbs = (path: string) => {
  if (!path || path === "/") {
    return "Control Center";
  }
  return path
    .split("/")
    .filter(Boolean)
    .map((segment) => segment.replace(/[-_]/g, " "))
    .join(" / ");
};

const Header = ({ title, breadcrumbPath, onToggleSidebar }: HeaderProps) => {
  const [currentTime, setCurrentTime] = useState(() => new Date());

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setCurrentTime(new Date());
    }, 60_000);
    return () => window.clearInterval(intervalId);
  }, []);

  const formattedTime = currentTime.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const handleRefresh = () => {
    window.dispatchEvent(new CustomEvent("app:refresh-data"));
  };

  return (
    <header className="app-header">
      <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
        <button
          type="button"
          className="action-button header__menu-button"
          onClick={onToggleSidebar}
          aria-label="Toggle navigation"
        >
          <FiMenu />
        </button>
        <div className="app-header__title">
          <h2>{title}</h2>
          <span className="app-header__breadcrumbs">{formatBreadcrumbs(breadcrumbPath)}</span>
        </div>
      </div>
      <div className="app-header__actions">
        <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-muted)", fontSize: "13px" }}>
          <FiClock />
          {formattedTime}
        </div>
        <button
          type="button"
          className="action-button"
          onClick={handleRefresh}
          title="Refresh dashboard data"
          aria-label="Refresh data"
        >
          <FiRefreshCcw />
          Refresh data
        </button>
        <button type="button" className="action-button" aria-label="Notifications">
          <FiBell />
        </button>
      </div>
    </header>
  );
};

export default Header;
