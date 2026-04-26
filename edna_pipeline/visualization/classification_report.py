"""HTML report builder for embedding classification results."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _fmt_float(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "0.00"


def _top_items(distribution: Dict[str, Any], limit: int = 10) -> List[Tuple[str, int]]:
    items: List[Tuple[str, int]] = []
    for key, value in distribution.items():
        try:
            items.append((str(key), int(value)))
        except (TypeError, ValueError):
            continue
    items.sort(key=lambda row: row[1], reverse=True)
    return items[:limit]


def _render_distribution_panel(title: str, distribution: Dict[str, Any], total: int) -> str:
    rows = _top_items(distribution, limit=12)
    if not rows:
        return f"""
<section class=\"panel\">
  <h3>{html.escape(title)}</h3>
  <p class=\"muted\">No values available.</p>
</section>
"""

    bars = []
    denominator = max(1, total)
    for name, count in rows:
        width = max(2.0, min(100.0, (count / denominator) * 100.0))
        bars.append(
            f"""
<div class=\"distribution-row\">
  <div class=\"distribution-row-header\">
    <span>{html.escape(name)}</span>
    <span>{count} ({_fmt_float((count / denominator) * 100.0, 1)}%)</span>
  </div>
  <div class=\"bar-track\"><div class=\"bar-fill\" style=\"width: {width:.2f}%\"></div></div>
</div>
"""
        )

    return f"""
<section class=\"panel\">
  <h3>{html.escape(title)}</h3>
  <div class=\"distribution-grid\">{''.join(bars)}</div>
</section>
"""


def _render_predictions_table(predictions: Iterable[Dict[str, Any]], limit: int = 200) -> str:
    rows = []
    for index, row in enumerate(predictions):
        if index >= limit:
            break
        rows.append(
            """
<tr>
  <td>{sequence_id}</td>
  <td>{kingdom}</td>
  <td>{phylum}</td>
  <td>{genus}</td>
  <td>{species}</td>
  <td>{confidence}</td>
  <td>{method}</td>
</tr>
""".format(
                sequence_id=html.escape(str(row.get("sequence_id", ""))),
                kingdom=html.escape(str(row.get("kingdom", "Unknown"))),
                phylum=html.escape(str(row.get("phylum", "Unknown"))),
                genus=html.escape(str(row.get("genus", "Unknown"))),
                species=html.escape(str(row.get("species", "Unknown"))),
                confidence=html.escape(f"{_fmt_float(row.get('confidence'), 2)}%"),
                method=html.escape(str(row.get("method", ""))),
            )
        )

    if not rows:
        rows.append("<tr><td colspan='7'>No classifications available.</td></tr>")

    return """
<section class=\"panel\">
  <h3>Per-Sequence Classification Preview</h3>
  <p class=\"muted\">Showing up to 200 sequences.</p>
  <div class=\"table-wrapper\">
    <table>
      <thead>
        <tr>
          <th>Sequence ID</th>
          <th>Kingdom</th>
          <th>Phylum / Cluster</th>
          <th>Genus</th>
          <th>Species</th>
          <th>Confidence</th>
          <th>Method</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</section>
""".format(rows="".join(rows))


def create_classification_html_report(
    report_path: str,
    sample_id: str,
    run_meta: Dict[str, Any],
    classification_results: Dict[str, Any],
    predictions: List[Dict[str, Any]],
) -> str:
    """Build and persist a professional HTML classification report."""
    output = Path(report_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    total = int(classification_results.get("total_classified") or 0)
    mean_conf = _fmt_float(classification_results.get("mean_confidence"), 2)
    mode = str(classification_results.get("classification_mode", "unknown"))
    classifier = str(classification_results.get("classifier", "unknown"))

    confidence_distribution = classification_results.get("confidence_distribution") or {}
    phylum_distribution = classification_results.get("phylum_distribution") or {}
    genus_distribution = classification_results.get("genus_distribution") or {}
    species_distribution = classification_results.get("species_distribution") or {}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    confidence_panel = _render_distribution_panel(
        "Confidence Distribution",
        confidence_distribution,
        total=max(1, sum(int(v) for v in confidence_distribution.values() if str(v).isdigit())),
    )

    html_content = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Classification Report - {html.escape(sample_id)}</title>
  <style>
    :root {{
      --bg-primary: #0b1324;
      --bg-secondary: #111c33;
      --bg-elevated: #182642;
      --accent: #2be38b;
      --accent-soft: rgba(43, 227, 139, 0.12);
      --text-primary: #f5f7fb;
      --text-secondary: #c8d3eb;
      --text-muted: #8591ac;
      --border-color: rgba(255, 255, 255, 0.08);
      --radius-lg: 18px;
      --radius-md: 12px;
      --shadow-soft: 0 18px 40px rgba(0, 0, 0, 0.35);
      --font-family: Inter, Segoe UI, Arial, sans-serif;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      padding: 28px;
      font-family: var(--font-family);
      color: var(--text-primary);
      background:
        radial-gradient(circle at top left, rgba(43, 227, 139, 0.08), transparent 40%),
        radial-gradient(circle at bottom right, rgba(43, 227, 139, 0.05), transparent 35%),
        var(--bg-primary);
      line-height: 1.45;
    }}

    .report {{
      max-width: 1280px;
      margin: 0 auto;
      display: grid;
      gap: 18px;
    }}

    .hero {{
      background: linear-gradient(135deg, rgba(24, 38, 66, 0.92), rgba(17, 28, 51, 0.95));
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-soft);
      padding: 24px;
      display: grid;
      gap: 10px;
    }}

    h1, h2, h3 {{ margin: 0; }}
    h1 {{ font-size: 28px; letter-spacing: 0.2px; }}
    h2 {{ font-size: 20px; }}
    h3 {{ font-size: 17px; color: var(--text-secondary); }}

    .muted {{ color: var(--text-muted); margin: 0; }}

    .cards {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }}

    .card {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 14px;
      display: grid;
      gap: 6px;
      min-width: 0;
    }}

    .label {{ color: var(--text-muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }}
    .value {{ font-size: 22px; font-weight: 650; word-break: break-all; min-width: 0; }}

    .grid-two {{
      display: grid;
      gap: 18px;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    }}

    .panel {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 18px;
      display: grid;
      gap: 10px;
    }}

    .distribution-grid {{ display: grid; gap: 8px; }}

    .distribution-row-header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 13px;
    }}

    .bar-track {{
      width: 100%;
      height: 8px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      overflow: hidden;
    }}

    .bar-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent), #0fbf76);
      border-radius: 999px;
    }}

    .table-wrapper {{ overflow-x: auto; }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 900px;
    }}

    th, td {{
      border-bottom: 1px solid var(--border-color);
      text-align: left;
      padding: 10px 8px;
      white-space: nowrap;
    }}

    th {{ color: var(--text-secondary); font-weight: 600; }}

    .footnote {{
      color: var(--text-muted);
      font-size: 12px;
      text-align: right;
    }}

    @media (max-width: 720px) {{
      body {{ padding: 14px; }}
      .hero {{ padding: 16px; }}
      .panel {{ padding: 14px; }}
      .value {{ font-size: 20px; }}
    }}
  </style>
</head>
<body>
  <main class=\"report\">
    <section class=\"hero\">
      <h1>eDNA Taxonomic Classification Report</h1>
      <p class=\"muted\">Sample <strong>{html.escape(sample_id)}</strong> • Generated {html.escape(now)}</p>
      <div class=\"cards\">
        <article class=\"card\"><div class=\"label\">Classified Sequences</div><div class=\"value\">{_fmt_int(total)}</div></article>
        <article class=\"card\"><div class=\"label\">Mean Confidence</div><div class=\"value\">{mean_conf}%</div></article>
        <article class=\"card\"><div class=\"label\">Classification Mode</div><div class=\"value\">{html.escape(mode)}</div></article>
        <article class=\"card\"><div class=\"label\">Classifier</div><div class=\"value\">{html.escape(classifier)}</div></article>
      </div>
      <p class=\"muted\">Run started: {html.escape(str(run_meta.get('start_time', 'n/a')))} • Completed: {html.escape(str(run_meta.get('end_time', 'n/a')))} • Duration: {_fmt_float(run_meta.get('processing_time', 0), 1)}s</p>
    </section>

    <section class=\"grid-two\">
      {_render_distribution_panel("Phylum / Cluster Composition", phylum_distribution, max(1, total))}
      {_render_distribution_panel("Genus Composition", genus_distribution, max(1, total))}
      {_render_distribution_panel("Species Composition", species_distribution, max(1, total))}
      {confidence_panel}
    </section>

    {_render_predictions_table(predictions, limit=200)}

    <p class=\"footnote\">This report is generated automatically from run artifacts and is intended for analytical review.</p>
  </main>
</body>
</html>
"""

    output.write_text(html_content, encoding="utf-8")
    return str(output)
