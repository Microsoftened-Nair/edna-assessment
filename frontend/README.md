# Deep-Sea eDNA Control Center (Frontend)

Modern, responsive control surface for the AI-driven deep-sea eDNA analysis pipeline. The interface is built with React, Vite, and TypeScript, featuring a dark theme with luminous green accents to mirror a deep-ocean mission control aesthetic.

## Highlights

- ✅ Dashboard with pipeline telemetry, diversity snapshots, and run history
- ⚙️ Wizards for launching single-sample or batch analyses
- 🗄️ Database catalog manager wired for NCBI reference downloads
- 📊 Detailed run and batch explorers with artifact access points
- 🧪 Mock API layer enabled by default; connect to real backend via `VITE_API_URL`

## Getting Started

```bash
cd frontend
npm install
npm run dev
```

The app defaults to mock data so you can explore the UI instantly. To connect to a backend API (FastAPI, Flask, etc.), set the following environment variables before running:

```bash
export VITE_API_URL="http://localhost:8000/api"
export VITE_USE_MOCK="false"
```

## Project Structure

```
frontend/
├── index.html
├── package.json
├── public/
│   └── favicon.svg
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── components/
│   ├── hooks/
│   ├── pages/
│   ├── services/
│   ├── styles/
│   └── types/
├── tsconfig.json
└── vite.config.ts
```

## Connecting to the Pipeline

The UI assumes a companion REST API surface wrapping the `DeepSeaEDNAPipeline`. Required endpoints:

- `GET /dashboard` – aggregate metrics for the dashboard cards
- `GET /runs/recent` – recent `PipelineRun` objects
- `GET /runs/{run_id}` – detail for a specific run
- `POST /runs` – trigger a new run
- `POST /runs/batch` and `GET /runs/batch/{batch_id}` – batch execution support
- `GET /databases` and `POST /databases/{name}/download` – database catalog operations

Refer to `src/services/api.ts` for expected payload shapes.

## Theming

Custom theming lives in `src/styles/global.css` and `src/styles/app.css`. Colors, shadows, and transitions are centralized through CSS variables for easy customization.

## Production Build

```bash
npm run build
npm run preview
```

Deploy the generated `dist/` folder to your static hosting or bundle it with the backend service.
