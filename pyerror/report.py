import sys
import os
import platform
from datetime import datetime
from typing import Optional
from pyerror.suggestions import SuggestionEngine
from pyerror.formatting import Formatter

def generate_markdown_report(exc: BaseException, file_path: Optional[str] = None) -> str:
    """
    Generates a beautifully formatted Markdown report for an exception,
    optionally saving it to a file.
    """
    details = SuggestionEngine.get_details(exc)
    frames = Formatter.extract_frames(exc)
    
    severity = getattr(exc, "__severity__", "ERROR").upper()
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    report_lines = [
        f"# 🚨 Error intelligence Report: {details['name']}",
        "",
        f"**Timestamp:** {timestamp}  ",
        f"**Severity:** `{severity}`  ",
        f"**Python Version:** {platform.python_version()}  ",
        f"**Platform:** {platform.platform()}  ",
        "",
        "## 💡 Explanation",
        "",
        f"> **{details['translation']}**",
        "",
        f"*Why it happened:* {details['why']}",
        "",
        "## 🛠️ Actionable Suggestions",
        ""
    ]
    
    for s in details["suggestions"]:
        report_lines.append(f"- [ ] {s}")
    report_lines.append("")
    
    if details["example"]:
        report_lines.extend([
            "### 📝 Correct Usage Reference",
            "```python",
            details["example"].strip(),
            "```",
            ""
        ])
        
    report_lines.extend([
        "## 🔍 Traceback Details",
        "",
        "```text"
    ])
    
    for f in frames:
        line_info = f"File \"{f['filename']}\", line {f['lineno']}, in {f['func_name']}"
        report_lines.append(line_info)
        if f["code_line"]:
            report_lines.append(f"    {f['code_line']}")
            
    report_lines.extend([
        "```",
        ""
    ])
    
    # Check for local variables in the last frame
    user_frames = [f for f in frames if f["is_user"]]
    active_frame = user_frames[-1] if user_frames else (frames[-1] if frames else None)
    
    if active_frame and active_frame["locals"]:
        report_lines.extend([
            "### 📦 Local Variables (Failing Scope)",
            "",
            "| Variable | Value |",
            "| :--- | :--- |"
        ])
        masked_locals = Formatter.mask_locals(active_frame["locals"])
        for k, v in masked_locals.items():
            report_lines.append(f"| `{k}` | `{v}` |")
        report_lines.append("")
        
    report_content = "\n".join(report_lines)
    
    if file_path:
        try:
            # Create parent directories if they don't exist
            parent = os.path.dirname(file_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(report_content)
        except Exception as e:
            sys.stderr.write(f"⚠️ error: failed to write markdown report to {file_path}: {e}\n")
            
    return report_content
