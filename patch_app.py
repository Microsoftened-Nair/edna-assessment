import re

with open("frontend/src/App.tsx", "r") as f:
    content = f.read()

# Add import
import_stmt = 'import EvalResults from "./pages/EvalResults";\nimport { FiBarChart2 } from "react-icons/fi";\n'
content = content.replace('import BatchDetails from "./pages/BatchDetails";', 'import BatchDetails from "./pages/BatchDetails";\n' + import_stmt)

# Add route
route_stmt = "  { path: \"/evaluation\", label: \"Evaluation\", element: <EvalResults />, icon: FiBarChart2, inSidebar: true },\n  { path: \"/settings\", label: \"Settings\""
content = content.replace('{ path: "/settings", label: "Settings"', route_stmt)

# Update react-icons
content = content.replace("FiSettings\n} from", "FiSettings,\n  FiBarChart2\n} from")

with open("frontend/src/App.tsx", "w") as f:
    f.write(content)

