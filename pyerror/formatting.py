import os
import sys
import traceback
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text
    from rich.markdown import Markdown
    from rich.theme import Theme
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Import suggestions engine
from pyerror.suggestions import SuggestionEngine

class Formatter:
    DEFAULT_SECRETS = ["password", "token", "secret", "key", "auth", "credential", "pwd", "pass", "ssn", "credit"]

    @classmethod
    def scrub_text(cls, text: str, secret_keys: List[str] = None) -> str:
        """Scrubs sensitive information (passwords, tokens, API keys) from raw text."""
        if not text:
            return text
        
        keys = secret_keys if secret_keys is not None else cls.DEFAULT_SECRETS
        
        # Scrub assignment values for matching keywords, e.g. password = "abc"
        # Matches key="val", key='val', key=val, key : val, etc.
        for key in keys:
            pattern = rf"(?i)\b({key})\b\s*([=:])\s*([\"']?)[^\s\"']+\3"
            text = re.sub(pattern, r"\1\2\3********\3", text)
            
        # Scrub potential Basic Auth credentials in URLs, e.g. http://user:pass@host
        auth_url_pattern = r"(?i)(https?://)([^:\s]+):([^@\s]+)@"
        text = re.sub(auth_url_pattern, r"\1\2:********@", text)
        
        # Scrub potential Credit Card numbers
        cc_pattern = r"\b(?:\d[ -]*?){13,16}\b"
        text = re.sub(cc_pattern, "********-CARD-********", text)
        
        return text

    @classmethod
    def is_user_frame(cls, filename: str) -> bool:
        """Determines if a frame belongs to user-written code."""
        if not filename:
            return False
        
        # Strip or normalize path
        filename = os.path.abspath(filename)
        
        # Check standard library paths
        std_lib_dir = os.path.dirname(os.__file__)
        if filename.startswith(std_lib_dir):
            return False
            
        # Check site-packages or venv
        if "site-packages" in filename or ".venv" in filename or "virtualenvs" in filename:
            return False
            
        # Ignore internal python wrappers / shims
        if filename.startswith("<") and filename.endswith(">"):
            if filename == "<stdin>":
                return True # interactive console
            return False
            
        return True

    @classmethod
    def extract_frames(cls, exc: BaseException) -> List[Dict[str, Any]]:
        """Walks the traceback and returns details of all frames with sensitive info scrubbed."""
        frames = []
        tb = exc.__traceback__
        while tb:
            frame = tb.tb_frame
            lineno = tb.tb_lineno
            filename = frame.f_code.co_filename
            func_name = frame.f_code.co_name
            
            # Extract line contents
            code_line = ""
            if os.path.exists(filename):
                try:
                    with open(filename, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        if 1 <= lineno <= len(lines):
                            code_line = cls.scrub_text(lines[lineno - 1].strip())
                except Exception:
                    pass
            
            # Capture local variables
            raw_locals = frame.f_locals
            captured_locals = {}
            for k, v in raw_locals.items():
                try:
                    captured_locals[k] = cls.scrub_text(repr(v))
                except Exception as e:
                    captured_locals[k] = f"<Unrepresentable: {type(e).__name__}>"

            frames.append({
                "filename": filename,
                "lineno": lineno,
                "func_name": func_name,
                "code_line": code_line,
                "locals": captured_locals,
                "is_user": cls.is_user_frame(filename)
            })
            tb = tb.tb_next
        return frames

    @classmethod
    def mask_locals(cls, locals_dict: Dict[str, str], mask_secrets: bool = True, secret_keys: List[str] = None) -> Dict[str, str]:
        """Masks sensitive values in local variables dictionary."""
        if not mask_secrets:
            return locals_dict
            
        keys_to_match = secret_keys if secret_keys is not None else cls.DEFAULT_SECRETS
        masked = {}
        
        for k, v in locals_dict.items():
            k_lower = k.lower()
            if any(secret in k_lower for secret in keys_to_match):
                masked[k] = "********"
            else:
                v_scrubbed = cls.scrub_text(v, keys_to_match)
                # Truncate overly long values
                if len(v_scrubbed) > 200:
                    masked[k] = v_scrubbed[:197] + "..."
                else:
                    masked[k] = v_scrubbed
        return masked

    @classmethod
    def format_cli(
        cls, 
        exc: BaseException, 
        mode: str = "full", 
        mask_secrets: bool = True, 
        secret_keys: List[str] = None
    ) -> str:
        """Formats the exception for the CLI."""
        details = SuggestionEngine.get_details(exc)
        frames = cls.extract_frames(exc)
        
        # Fallback to plain formatting if Rich is not installed
        if not RICH_AVAILABLE:
            return cls._format_cli_plain(exc, details, frames, mode, mask_secrets, secret_keys)
            
        console = Console(color_system="truecolor", stderr=True)
        
        # Build Title/Severity style
        severity = "ERROR"
        if hasattr(exc, "__severity__"):
            severity = str(exc.__severity__).upper()
            
        severity_colors = {
            "INFO": "bold cyan",
            "WARNING": "bold yellow",
            "ERROR": "bold red",
            "CRITICAL": "bold white on red"
        }
        color = severity_colors.get(severity, "bold red")
        
        title_text = Text(f"[{severity}] {details['name']}: {details['message']}", style=color)
        
        # 1. Explanation panel
        explanation_content = f"[bold]Explanation:[/bold]\n{details['translation']}\n\n[bold]Why it happened:[/bold]\n{details['why']}"
        explanation_panel = Panel(
            explanation_content,
            title="💡 Error Intelligence",
            title_align="left",
            border_style="cyan",
            padding=(1, 2)
        )
        
        # 2. Traceback section
        traceback_text = Text()
        user_frames = [f for f in frames if f["is_user"]]
        
        # Which frames to display?
        frames_to_display = frames
        if mode == "beginner":
            # Beginner mode: only show the very last user frame, or the last frame if no user frame exists
            frames_to_display = [user_frames[-1]] if user_frames else [frames[-1]]
        elif mode == "compact":
            # Compact mode: show all user frames
            frames_to_display = user_frames if user_frames else frames

        # Build traceback list
        traceback_table = Table(show_header=False, box=None, padding=(0, 1))
        traceback_table.add_column("Location", style="dim")
        traceback_table.add_column("Code", style="bold white")
        
        for f in frames_to_display:
            relative_path = os.path.basename(f["filename"])
            location = f"{relative_path}:{f['lineno']} in {f['func_name']}"
            
            # Syntax highlight code line
            syntax_line = ""
            if f["code_line"]:
                # Wrap code line in Syntax highlighter
                syntax_line = Syntax(f["code_line"], "python", theme="monokai", line_numbers=False)
            
            traceback_table.add_row(location, syntax_line or "<no source code>")
            
            # Show locals for each displayed frame in full mode, or for the active frame in compact mode
            show_locals = (mode == "full") or (mode == "compact" and f == frames_to_display[-1])
            if show_locals and f["locals"]:
                masked_l = cls.mask_locals(f["locals"], mask_secrets, secret_keys)
                locals_table = Table(title="Local variables:", title_style="italic dim yellow", title_align="left", show_header=True, header_style="bold dim magenta", box=None, padding=(0, 2))
                locals_table.add_column("Variable", style="cyan")
                locals_table.add_column("Value", style="green")
                
                for k, v in masked_l.items():
                    locals_table.add_row(k, v)
                
                traceback_table.add_row("", locals_table)
                traceback_table.add_row("", "") # spacer
                
        traceback_panel = Panel(
            traceback_table,
            title="🔍 Traceback (Filtered)" if mode in ("beginner", "compact") else "🔍 Complete Traceback",
            title_align="left",
            border_style="magenta",
            padding=(1, 2)
        )
        
        # 3. Suggestions Panel
        sug_content = "\n".join(f"• {s}" for s in details["suggestions"])
        if details["example"]:
            sug_content += f"\n\n[bold]Example of correct usage:[/bold]\n"
            
        suggestions_panel = Panel(
            sug_content,
            title="🛠️ Actionable Suggestions",
            title_align="left",
            border_style="green",
            padding=(1, 2)
        )
        
        # Output buffering using Console
        with console.capture() as capture:
            console.print("\n")
            console.print(title_text)
            console.print(explanation_panel)
            console.print(traceback_panel)
            console.print(suggestions_panel)
            if details["example"]:
                # Print code example outside or inside the panel. Inside is nicer, let's print syntax block.
                syntax_example = Syntax(details["example"], "python", theme="monokai", line_numbers=False)
                console.print(Panel(syntax_example, title="📝 Code Reference", border_style="green", padding=(0, 2)))
            console.print("\n")
            
        return capture.get()

    @classmethod
    def _format_cli_plain(
        cls, 
        exc: BaseException, 
        details: Dict[str, Any], 
        frames: List[Dict[str, Any]], 
        mode: str, 
        mask_secrets: bool, 
        secret_keys: List[str]
    ) -> str:
        """Plain ANSI/Text traceback formatter fallback."""
        lines = []
        severity = getattr(exc, "__severity__", "ERROR").upper()
        lines.append(f"=== [{severity}] {details['name']}: {details['message']} ===")
        lines.append("")
        lines.append("💡 Error Explanation:")
        lines.append(details['translation'])
        lines.append(details['why'])
        lines.append("")
        
        lines.append("🔍 Traceback:")
        user_frames = [f for f in frames if f["is_user"]]
        frames_to_display = frames
        if mode == "beginner":
            frames_to_display = [user_frames[-1]] if user_frames else [frames[-1]]
        elif mode == "compact":
            frames_to_display = user_frames if user_frames else frames
            
        for f in frames_to_display:
            lines.append(f"  File \"{f['filename']}\", line {f['lineno']}, in {f['func_name']}")
            if f["code_line"]:
                lines.append(f"    {f['code_line']}")
            
            show_locals = (mode == "full") or (mode == "compact" and f == frames_to_display[-1])
            if show_locals and f["locals"]:
                masked_l = cls.mask_locals(f["locals"], mask_secrets, secret_keys)
                lines.append("    Local variables:")
                for k, v in masked_l.items():
                    lines.append(f"      {k} = {v}")
            lines.append("")
            
        lines.append("🛠️ Suggestions:")
        for s in details["suggestions"]:
            lines.append(f"  * {s}")
            
        if details["example"]:
            lines.append("")
            lines.append("📝 Correct Usage Example:")
            lines.append(details["example"])
            
        return "\n".join(lines)

    @classmethod
    def format_json(cls, exc: BaseException, mask_secrets: bool = True, secret_keys: List[str] = None) -> str:
        """Formats the exception details into a production-ready JSON string."""
        details = SuggestionEngine.get_details(exc)
        frames = cls.extract_frames(exc)
        
        # Build structure
        serialized_frames = []
        for f in frames:
            masked_l = cls.mask_locals(f["locals"], mask_secrets, secret_keys)
            serialized_frames.append({
                "filename": f["filename"],
                "lineno": f["lineno"],
                "func_name": f["func_name"],
                "code_line": f["code_line"],
                "locals": masked_l,
                "is_user": f["is_user"]
            })
            
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "severity": getattr(exc, "__severity__", "ERROR").upper(),
            "exception": {
                "type": details["name"],
                "message": details["message"]
            },
            "explanation": {
                "translation": details["translation"],
                "why": details["why"]
            },
            "suggestions": details["suggestions"],
            "traceback": serialized_frames
        }
        return json.dumps(payload, indent=2)

    @classmethod
    def format_jupyter_html(
        cls, 
        exc: BaseException, 
        mask_secrets: bool = True, 
        secret_keys: List[str] = None
    ) -> str:
        """Generates premium styled HTML representation for Jupyter Notebooks."""
        details = SuggestionEngine.get_details(exc)
        frames = cls.extract_frames(exc)
        severity = getattr(exc, "__severity__", "ERROR").upper()
        
        # Color palettes based on severity
        severity_styles = {
            "INFO": ("#06b6d4", "rgba(6, 182, 212, 0.1)"),
            "WARNING": ("#f59e0b", "rgba(245, 158, 11, 0.1)"),
            "ERROR": ("#ef4444", "rgba(239, 68, 68, 0.1)"),
            "CRITICAL": ("#b91c1c", "rgba(185, 28, 28, 0.15)")
        }
        primary_color, bg_color = severity_styles.get(severity, ("#ef4444", "rgba(239, 68, 68, 0.1)"))

        # Build list of user frames
        traceback_html_list = []
        for i, f in enumerate(frames):
            escaped_filename = f["filename"].replace("\\", "/")
            masked_l = cls.mask_locals(f["locals"], mask_secrets, secret_keys)
            locals_rows = []
            for k, v in masked_l.items():
                locals_rows.append(f"<tr><td style='color:#a855f7; padding: 2px 10px 2px 0;'><b>{k}</b></td><td style='color:#22c55e;'>{v}</td></tr>")
                
            locals_section = ""
            if locals_rows:
                locals_section = f"""
                <div style="margin-top: 8px; font-size: 0.9em; background: rgba(0,0,0,0.02); padding: 8px 12px; border-left: 2px solid #a855f7;">
                    <div style="color: #64748b; font-weight: bold; margin-bottom: 4px;">Local Variables:</div>
                    <table style="border: none; border-collapse: collapse; background: transparent; width: auto; font-family: monospace;">
                        {"".join(locals_rows)}
                    </table>
                </div>
                """
            
            frame_bg = "#fef2f2" if f["is_user"] else "transparent"
            frame_border = "1px solid #fee2e2" if f["is_user"] else "1px solid #f1f5f9"
            
            traceback_html_list.append(f"""
            <div style="margin-bottom: 8px; padding: 10px; background: {frame_bg}; border: {frame_border}; border-radius: 6px;">
                <div style="font-size: 0.85em; color: #64748b; margin-bottom: 4px;">
                    File <span style="color: #4f46e5; font-family: monospace;">{escaped_filename}</span>, line <b>{f['lineno']}</b>, in <b>{f['func_name']}</b>
                </div>
                <div style="background: #1e1e1e; padding: 6px 12px; border-radius: 4px; color: #f8f8f2; font-family: monospace; font-size: 0.9em; overflow-x: auto;">
                    <code>{f['code_line'] or '# source not available'}</code>
                </div>
                {locals_section}
            </div>
            """)

        # Assemble suggestions
        sug_items = "".join(f"<li style='margin-bottom: 6px;'>{s}</li>" for s in details["suggestions"])
        
        example_block = ""
        if details["example"]:
            example_block = f"""
            <div style="margin-top: 15px;">
                <div style="font-weight: bold; color: #1e293b; margin-bottom: 5px;">📝 Correct Usage Reference:</div>
                <div style="background: #1e1e1e; padding: 12px; border-radius: 6px; color: #f8f8f2; font-family: monospace; font-size: 0.9em; overflow-x: auto; white-space: pre;">{details['example']}</div>
            </div>
            """

        # Complete HTML with sleek glassmorphism design
        html = f"""
        <div style="
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-left: 6px solid {primary_color};
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            max-width: 900px;
        ">
            <!-- Header -->
            <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #f1f5f9; padding-bottom: 12px; margin-bottom: 16px;">
                <div>
                    <span style="
                        background: {bg_color}; 
                        color: {primary_color}; 
                        padding: 3px 8px; 
                        border-radius: 4px; 
                        font-weight: bold; 
                        font-size: 0.8em; 
                        letter-spacing: 0.05em;
                        border: 1px solid {primary_color}44;
                        margin-right: 10px;
                    ">{severity}</span>
                    <span style="font-size: 1.25em; font-weight: 700; color: #1e293b;">{details['name']}</span>
                </div>
                <div style="font-size: 0.85em; color: #94a3b8; font-style: italic;">Error Intelligence Active</div>
            </div>

            <!-- Message -->
            <div style="font-size: 1.05em; font-family: monospace; color: #ef4444; margin-bottom: 16px; padding: 8px 12px; background: #fff5f5; border-radius: 6px; border: 1px solid #fee2e2;">
                {details['message']}
            </div>

            <!-- Explanation Panel -->
            <div style="background: #ecfeff; border: 1px solid #cffafe; border-radius: 6px; padding: 14px; margin-bottom: 16px;">
                <div style="font-weight: bold; color: #0891b2; font-size: 0.95em; display: flex; align-items: center; margin-bottom: 6px;">
                    <span style="margin-right: 6px;">💡</span> Explanation & Details
                </div>
                <div style="color: #155e75; font-size: 0.95em; line-height: 1.5; margin-bottom: 8px;">
                    {details['translation']}
                </div>
                <div style="color: #0e7490; font-size: 0.9em; font-style: italic;">
                    <b>Reason:</b> {details['why']}
                </div>
            </div>

            <!-- Traceback Accordion / Section -->
            <details style="margin-bottom: 16px; outline: none;">
                <summary style="cursor: pointer; font-weight: bold; color: #475569; font-size: 0.95em; padding: 6px 0; outline: none; user-select: none;">
                    🔍 Traceback details (click to expand)
                </summary>
                <div style="margin-top: 10px; border-left: 2px dashed #cbd5e1; padding-left: 12px;">
                    {"".join(traceback_html_list)}
                </div>
            </details>

            <!-- Suggestions Panel -->
            <div style="background: #f0fdf4; border: 1px solid #dcfce7; border-radius: 6px; padding: 14px;">
                <div style="font-weight: bold; color: #16a34a; font-size: 0.95em; margin-bottom: 8px; display: flex; align-items: center;">
                    <span style="margin-right: 6px;">🛠️</span> Actionable Suggestions
                </div>
                <ul style="color: #166534; font-size: 0.95em; line-height: 1.5; padding-left: 20px; margin: 0;">
                    {sug_items}
                </ul>
                {example_block}
            </div>
        </div>
        """
        return html

class JupyterHtmlWrapper:
    """Helper class to wrap HTML tracebacks for Jupyter _repr_html_ response."""
    def __init__(self, html: str):
        self.html = html
        
    def _repr_html_(self) -> str:
        return self.html
