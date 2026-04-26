import { ReactNode, useMemo, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import {
  FiActivity,
  FiGrid,
  FiLayers,
  FiList,
  FiPlayCircle,
  FiSettings,
  FiBarChart2
} from "react-icons/fi";
import Sidebar, { SidebarNavItem } from "./components/Sidebar";
import Header from "./components/Header";
import Dashboard from "./pages/Dashboard";
import SingleRun from "./pages/SingleRun";
import BatchRuns from "./pages/BatchRuns";
import Results from "./pages/Results";
import Settings from "./pages/Settings";
import Logs from "./pages/Logs";
import RunDetails from "./pages/RunDetails";
import BatchDetails from "./pages/BatchDetails";
import EvalResults from "./pages/EvalResults";
import "./styles/app.css";

type RouteConfig = {
  path: string;
  label: string;
  element: ReactNode;
  icon?: SidebarNavItem["icon"];
  inSidebar?: boolean;
};

const routes: RouteConfig[] = [
  { path: "/", label: "Dashboard", element: <Dashboard />, icon: FiGrid, inSidebar: true },
  { path: "/runs/new", label: "Single Run", element: <SingleRun />, icon: FiPlayCircle, inSidebar: true },
  { path: "/runs/batch", label: "Batch Runs", element: <BatchRuns />, icon: FiLayers, inSidebar: true },
  { path: "/results", label: "Results", element: <Results />, icon: FiActivity, inSidebar: true },
  { path: "/evaluation", label: "Evaluation", element: <EvalResults />, icon: FiBarChart2, inSidebar: true },
  { path: "/settings", label: "Settings", element: <Settings />, icon: FiSettings, inSidebar: true },
  { path: "/logs", label: "Logs", element: <Logs />, icon: FiList, inSidebar: true },
  { path: "/results/:runId", label: "Run Details", element: <RunDetails /> },
  { path: "/runs/batch/:batchId", label: "Batch Details", element: <BatchDetails /> }
];

const App = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  const navItems = useMemo<SidebarNavItem[]>(
    () =>
      routes
        .filter((route) => route.inSidebar)
        .map((route) => ({
          path: route.path,
          label: route.label,
          icon: route.icon ?? FiGrid
        })),
    []
  );

  const activeRoute = useMemo(() => {
    return routes.find((route) => {
      if (route.path === "/") {
        return location.pathname === "/";
      }
      return location.pathname.startsWith(route.path.replace(/:\w+/, ""));
    });
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <Sidebar
        items={navItems}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      {sidebarOpen ? <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} /> : null}
      <div className="app-main">
        <Header
          title={activeRoute?.label ?? "Control Center"}
          breadcrumbPath={location.pathname}
          onToggleSidebar={() => setSidebarOpen((value) => !value)}
        />
        <main className="app-content">
          <Routes>
            {routes.map((route) => (
              <Route key={route.path} path={route.path} element={route.element} />
            ))}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
};

export default App;
