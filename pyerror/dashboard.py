"""
Tiny self-hosted Flask dashboard.

`serve(host, port)` runs the dev server; `create_app()` returns the
Flask app for testing. Requires Flask::

    pip install pyerror-intel[dashboard]
"""
from __future__ import annotations

import json
import os
from typing import Optional

try:
    from flask import Flask, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False


_TEMPLATE = """<!doctype html>
<html><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="10">
<title>pyerror dashboard</title>
<style>
  body{background:#0f172a;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:24px;}
  h1{color:#f87171;}
  table{width:100%;border-collapse:collapse;margin-top:16px;}
  th,td{border-bottom:1px solid #334155;padding:8px;text-align:left;font-size:0.92em;}
  th{color:#94a3b8;}
  .pill{background:#334155;border-radius:999px;padding:2px 8px;font-size:0.8em;}
  .err{color:#f87171;}
</style></head><body>
<h1>pyerror dashboard</h1>
<p>Total signatures: %TOTAL% · Recorded errors: %COUNT%</p>
<h2>Top errors</h2>
<table><thead><tr><th>Signature</th><th>Count</th><th>Release</th><th>Fingerprint</th><th>Last seen</th></tr></thead><tbody>
%ROWS%
</tbody></table>
<h2>By release</h2>
<table><thead><tr><th>Release</th><th>Count</th></tr></thead><tbody>%RELEASE_ROWS%</tbody></table>
</body></html>"""


def create_app(analytics_path: Optional[str] = None):
    if not FLASK_AVAILABLE:
        raise ImportError("pyerror dashboard requires `pip install pyerror-intel[dashboard]`.")
    app = Flask("pyerror.dashboard")

    def _tracker():
        from pyerror.analytics import AnalyticsTracker
        return AnalyticsTracker(filename=analytics_path) if analytics_path else AnalyticsTracker()

    @app.route("/")
    def index():
        tracker = _tracker()
        data = tracker.data
        total = len(data)
        count = sum(r.get("count", 0) for r in data.values())
        sorted_items = sorted(data.items(), key=lambda kv: kv[1].get("count", 0), reverse=True)[:50]
        rows = []
        for sig, info in sorted_items:
            rows.append("<tr><td class='err'>{}</td><td>{}</td><td>{}</td><td><code>{}</code></td><td>{}</td></tr>".format(
                _esc(sig)[:140], info.get("count", 0), _esc(info.get("release") or "-"),
                _esc(info.get("fingerprint") or "-"), _esc(info.get("last_seen") or "")))
        from pyerror.analytics import releases_summary
        rel_rows = []
        for rel, n in releases_summary().items():
            rel_rows.append("<tr><td>{}</td><td>{}</td></tr>".format(_esc(rel), n))
        html = (_TEMPLATE
                .replace("%TOTAL%", str(total))
                .replace("%COUNT%", str(count))
                .replace("%ROWS%", "".join(rows) or "<tr><td colspan='5'>No errors yet.</td></tr>")
                .replace("%RELEASE_ROWS%", "".join(rel_rows) or "<tr><td colspan='2'>No data.</td></tr>"))
        return html

    @app.route("/api/analytics")
    def api_analytics():
        return jsonify(_tracker().data)

    @app.route("/api/clusters")
    def api_clusters():
        try:
            from pyerror.clustering import cluster_errors
            clusters = cluster_errors(_tracker().data)
            return jsonify([{
                "fingerprint": c.fingerprint,
                "count": c.count,
                "signatures": list(c.signatures),
                "first_seen": c.first_seen,
                "last_seen": c.last_seen,
            } for c in clusters])
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return app


def _esc(text):
    return (str(text or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def serve(host: str = "127.0.0.1", port: int = 8765,
          analytics_path: Optional[str] = None,
          open_browser: bool = False) -> None:
    app = create_app(analytics_path)
    if open_browser:
        try:
            import webbrowser
            webbrowser.open("http://{}:{}".format(host, port))
        except Exception:
            pass
    app.run(host=host, port=port, debug=False)
