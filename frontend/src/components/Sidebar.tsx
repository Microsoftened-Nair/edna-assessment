import { FiX } from "react-icons/fi";
import type { IconType } from "react-icons";
import { NavLink } from "react-router-dom";
import clsx from "clsx";

export interface SidebarNavItem {
  path: string;
  label: string;
  icon: IconType;
}

interface SidebarProps {
  items: SidebarNavItem[];
  open: boolean;
  onClose: () => void;
}

const Sidebar = ({ items, open, onClose }: SidebarProps) => {
  return (
    <aside className={clsx("sidebar", { "sidebar--open": open })}>
      <div className="sidebar__brand">
        <div className="sidebar__brand-icon">ED</div>
        <div>
          <h1>Deep-Sea eDNA</h1>
          <span>AI Control Center</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="action-button sidebar__close"
          aria-label="Close navigation"
        >
          <FiX />
        </button>
      </div>

      <nav className="sidebar__nav">
        {items.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              clsx("nav-link", { active: isActive })
            }
            onClick={() => onClose()}
          >
            <item.icon />
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* <div className="sidebar__cta">
        <div>
          <div className="sidebar__cta-title">Realtime Monitoring</div>
          <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
            Enable WebSocket streaming to see pipeline events as they happen.
          </div>
        </div>
        <button type="button" disabled title="Realtime monitoring is coming soon">
          Enable stream
          <FiArrowRight />
        </button>
      </div> */}

      <div className="sidebar__footer">
        <div>v1.0.0 • AI-driven biodiversity intelligence</div>
      </div>
    </aside>
  );
};

export default Sidebar;
