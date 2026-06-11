import os
import json
import traceback
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

class AnalyticsReport:
    """Wrapper for displaying error analytics in CLI and Jupyter."""
    def __init__(self, data: Dict[str, Any]):
        self.data = data

    def __str__(self) -> str:
        if not self.data:
            return "No errors recorded yet."
            
        lines = ["=== Error Intelligence Analytics ===", ""]
        # Sort by count descending
        sorted_errors = sorted(self.data.items(), key=lambda item: item[1]["count"], reverse=True)
        for sig, info in sorted_errors:
            lines.append(f"{sig} -> {info['count']} times")
            lines.append(f"  First seen: {info['first_seen']}")
            lines.append(f"  Last seen:  {info['last_seen']}")
            lines.append("")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.__str__()

    def show(self):
        """Prints a beautiful summary table of recurring errors."""
        if not self.data:
            if RICH_AVAILABLE:
                Console(stderr=True).print("[italic dim]No errors recorded yet.[/italic dim]")
            else:
                print("No errors recorded yet.")
            return

        if not RICH_AVAILABLE:
            print(self.__str__())
            return

        console = Console(stderr=True)
        table = Table(title="📊 Recurring Errors Grouping & Count", title_style="bold cyan", header_style="bold magenta")
        table.add_column("Error Signature", style="white", ratio=3)
        table.add_column("Count", style="green bold", justify="right")
        table.add_column("Last Occurred", style="dim cyan")

        sorted_errors = sorted(self.data.items(), key=lambda item: item[1]["count"], reverse=True)
        for sig, info in sorted_errors:
            # Parse signature to make it look nicer
            sig_text = Text(sig)
            if ":" in sig:
                parts = sig.split(":", 1)
                sig_text = Text(parts[0], style="bold red")
                sig_text.append(":" + parts[1], style="white")

            # Format time
            last_seen_dt = info['last_seen']
            if "T" in last_seen_dt:
                last_seen_dt = last_seen_dt.split("T")[1][:8] # Just show HH:MM:SS

            table.add_row(sig_text, str(info["count"]), last_seen_dt)

        console.print(Panel(
            table,
            title="Analytics Report",
            title_align="left",
            border_style="cyan",
            padding=(1, 2)
        ))

    def _repr_html_(self) -> str:
        """HTML representation with visual frequency bars for Jupyter Notebooks."""
        if not self.data:
            return "<div style='color: #64748b; font-style: italic;'>No errors recorded yet.</div>"

        sorted_errors = sorted(self.data.items(), key=lambda item: item[1]["count"], reverse=True)
        max_count = max(item["count"] for item in self.data.values())

        rows = []
        for sig, info in sorted_errors:
            percentage = (info["count"] / max_count) * 100
            
            # Split sig into name and details
            err_name = sig
            err_msg = ""
            if ":" in sig:
                err_name, err_msg = sig.split(":", 1)
                
            last_seen_clean = info['last_seen'].replace("T", " ")[:19]
            
            rows.append(f"""
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px 0; font-family: monospace; font-size: 0.9em; vertical-align: top; max-width: 400px; overflow-wrap: break-word;">
                    <b style="color: #ef4444;">{err_name}</b><span style="color: #475569;">{err_msg}</span>
                </td>
                <td style="padding: 10px 10px; text-align: right; font-weight: bold; color: #1e293b; font-size: 0.95em; vertical-align: top;">
                    {info['count']}
                </td>
                <td style="padding: 10px 10px; width: 160px; vertical-align: middle;">
                    <div style="background: #e2e8f0; border-radius: 4px; height: 12px; width: 100%;">
                        <div style="background: linear-gradient(90deg, #f87171, #ef4444); height: 100%; border-radius: 4px; width: {percentage}%;"></div>
                    </div>
                </td>
                <td style="padding: 10px 0; font-size: 0.85em; color: #64748b; vertical-align: top; text-align: right;">
                    {last_seen_clean}
                </td>
            </tr>
            """)

        html = f"""
        <div style="
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            max-width: 800px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        ">
            <div style="font-weight: bold; color: #0f172a; font-size: 1.1em; margin-bottom: 15px; display: flex; align-items: center; justify-content: space-between;">
                <span>📊 Recurring Error Diagnostics (Analytics)</span>
                <span style="font-size: 0.8em; color: #64748b; font-weight: normal;">Cross-Run Tracking</span>
            </div>
            <table style="border: none; border-collapse: collapse; width: 100%; text-align: left;">
                <thead>
                    <tr style="border-bottom: 2px solid #cbd5e1; color: #475569; font-size: 0.85em; font-weight: bold;">
                        <th style="padding-bottom: 8px; text-align: left;">Error Signature</th>
                        <th style="padding-bottom: 8px; text-align: right; padding-right: 10px;">Frequency</th>
                        <th style="padding-bottom: 8px; text-align: left;">Visual</th>
                        <th style="padding-bottom: 8px; text-align: right;">Last Occurred</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
        </div>
        """
        return html

class AnalyticsTracker:
    def __init__(self, filename: str = ".error_analytics.json"):
        self.filename = filename
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def record_exception(self, exc: BaseException):
        """Groups and records an exception occurrence."""
        exc_type = type(exc).__name__
        exc_msg = str(exc)
        
        # Determine the location signature (last frame in traceback)
        location = "unknown"
        tb = exc.__traceback__
        if tb:
            # Walk to the last frame
            last_frame = tb
            while last_frame.tb_next:
                last_frame = last_frame.tb_next
            
            filename = os.path.basename(last_frame.tb_frame.f_code.co_filename)
            lineno = last_frame.tb_lineno
            func_name = last_frame.tb_frame.f_code.co_name
            location = f"{filename}:{lineno} in {func_name}"

        # Signature: ExceptionType: message @ location
        signature = f"{exc_type}: {exc_msg} (@ {location})"
        now_str = datetime.utcnow().isoformat() + "Z"

        if signature in self.data:
            self.data[signature]["count"] += 1
            self.data[signature]["last_seen"] = now_str
        else:
            self.data[signature] = {
                "count": 1,
                "first_seen": now_str,
                "last_seen": now_str,
                "location": location,
                "type": exc_type,
                "message": exc_msg
            }
        self._save()

    def get_report(self) -> AnalyticsReport:
        """Returns the analytics report wrapper."""
        return AnalyticsReport(self.data)

    def clear(self):
        """Clears all logged analytics."""
        self.data = {}
        if os.path.exists(self.filename):
            try:
                os.remove(self.filename)
            except Exception:
                pass

# Global instance
_tracker = AnalyticsTracker()

def log_error(exc: BaseException):
    """Global hook helper to log exceptions automatically."""
    _tracker.record_exception(exc)

def get_analytics() -> AnalyticsReport:
    """Public API to fetch the error analytics report."""
    return _tracker.get_report()

def clear_analytics():
    """Public API to clear the logged error analytics."""
    _tracker.clear()
