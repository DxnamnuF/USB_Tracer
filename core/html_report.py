from html import escape
from pathlib import Path

from .relationship_graph import build_relationship_edges


def h(value):
    if value is None:
        return ""
    return escape(str(value))


def join_values(values):
    return ", ".join(str(x) for x in values or [] if x)


def build_summary_rows(summary):
    rows = []
    for item in summary:
        rows.append(f"""
<tr>
  <td>{h(item.get('friendly_name') or item.get('device_key'))}</td>
  <td>{h(item.get('device_class'))}</td>
  <td>{h(item.get('serial'))}</td>
  <td>{h(item.get('first_seen_utc') or item.get('first_seen_local'))}</td>
  <td>{h(item.get('last_seen_utc') or item.get('last_seen_local'))}</td>
  <td>{h(item.get('evidence_count'))}</td>
  <td>{h(join_values(item.get('drive_letters')))}</td>
  <td>{h(join_values(item.get('volume_guids')))}</td>
  <td>{h(join_values(item.get('sources')))}</td>
</tr>""")
    return "\n".join(rows)


def build_timeline_rows(timeline):
    rows = []
    for item in timeline:
        device = item.get("friendly_name") or item.get("matched_registry_name") or item.get("device_instance_id") or item.get("artifact_source")
        source = item.get("channel") if item.get("event_kind") == "eventlog" else item.get("artifact_type")
        rows.append(f"""
<tr>
  <td>{h(item.get('timestamp_utc') or item.get('timestamp_local'))}</td>
  <td>{h(item.get('event_kind'))}</td>
  <td>{h(source)}</td>
  <td>{h(item.get('action_text'))}</td>
  <td>{h(device)}</td>
  <td>{h(item.get('device_class'))}</td>
  <td>{h(item.get('serial'))}</td>
  <td>{h(join_values(item.get('drive_letters') or ([item.get('drive_letter')] if item.get('drive_letter') else [])))}</td>
  <td>{h(join_values(item.get('volume_guids') or ([item.get('volume_guid')] if item.get('volume_guid') else [])))}</td>
  <td>{h(item.get('match_confidence'))}</td>
  <td>{h(item.get('message_short'))}</td>
</tr>""")
    return "\n".join(rows)


def build_graph_rows(timeline, summary):
    rows = []
    for edge in build_relationship_edges(timeline, summary):
        rows.append(f"<tr><td>{h(edge.get('from'))}</td><td>{h(edge.get('relation'))}</td><td>{h(edge.get('to'))}</td></tr>")
    return "\n".join(rows)


def save_html_report(path, timeline, summary, title="DFIR_project Report"):
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{h(title)}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; background: #f6f7f9; color: #111; }}
h1, h2 {{ margin-bottom: 8px; }}
.card {{ background: white; border-radius: 10px; padding: 18px; margin-bottom: 22px; box-shadow: 0 1px 5px rgba(0,0,0,.08); }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #ddd; padding: 7px; vertical-align: top; }}
th {{ background: #eceff3; text-align: left; }}
.small {{ color: #555; font-size: 13px; }}
</style>
</head>
<body>
<h1>{h(title)}</h1>
<p class="small">This report was generated automatically. Registry LastWrite, setupapi.dev.log timestamps, file modification times, and Event Log timestamps must be interpreted together and should not be treated as standalone proof of physical USB insertion.</p>

<div class="card">
<h2>Device summary: first seen / last seen</h2>
<table>
<thead>
<tr>
  <th>Device</th><th>Class</th><th>Serial</th><th>First seen</th><th>Last seen</th>
  <th>Evidence</th><th>Drive letters</th><th>Volume GUIDs</th><th>Sources</th>
</tr>
</thead>
<tbody>{build_summary_rows(summary)}</tbody>
</table>
</div>

<div class="card">
<h2>Relationship graph edges</h2>
<table>
<thead><tr><th>From</th><th>Relation</th><th>To</th></tr></thead>
<tbody>{build_graph_rows(timeline, summary)}</tbody>
</table>
</div>

<div class="card">
<h2>Full timeline</h2>
<table>
<thead>
<tr>
  <th>Time</th><th>Kind</th><th>Source</th><th>Action</th><th>Device</th><th>Class</th>
  <th>Serial</th><th>Drive</th><th>Volume GUID</th><th>Match</th><th>Note</th>
</tr>
</thead>
<tbody>{build_timeline_rows(timeline)}</tbody>
</table>
</div>
</body>
</html>"""
    Path(path).write_text(html, encoding="utf-8")
