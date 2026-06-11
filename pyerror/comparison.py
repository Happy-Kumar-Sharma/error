import sys
from typing import Any, Dict, List, Optional, Type, Union

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

class ComparisonResult:
    """Wrapper class for comparison output, with custom CLI and Jupyter rendering."""
    def __init__(self, expected: Any, got: Any, value: Any = None):
        self.expected = expected
        self.got = got
        self.value = value
        
        # Analyze types and values
        self.expected_type = expected if isinstance(expected, type) else type(expected)
        self.got_type = got if isinstance(got, type) else type(got)
        
        self.is_type_only = isinstance(expected, type) and isinstance(got, type)
        
        self.expected_val_repr = str(expected) if not isinstance(expected, type) else None
        self.got_val_repr = str(got) if not isinstance(got, type) else None
        if value is not None:
            self.got_val_repr = str(value)
            
        self.suggestion = self._generate_suggestion()

    def _generate_suggestion(self) -> str:
        t_exp = self.expected_type
        t_got = self.got_type
        
        if t_exp == int and t_got == str:
            val_placeholder = f'"{self.got_val_repr}"' if self.got_val_repr else "value"
            return f"int({val_placeholder})"
        elif t_exp == str and t_got == int:
            val_placeholder = str(self.got_val_repr) if self.got_val_repr else "value"
            return f"str({val_placeholder})"
        elif t_exp == float and t_got == str:
            val_placeholder = f'"{self.got_val_repr}"' if self.got_val_repr else "value"
            return f"float({val_placeholder})"
        elif t_exp == list and t_got == tuple:
            return "list(value)"
        elif t_exp == tuple and t_got == list:
            return "tuple(value)"
        elif t_got == type(None):
            return f"Ensure the value is not None before using it, or provide a default fallback."
        else:
            return f"Convert {t_got.__name__} to {t_exp.__name__} or check variable assignments."

    def __str__(self) -> str:
        lines = []
        if self.is_type_only:
            lines.append(f"expected: {self.expected_type.__name__}")
            lines.append(f"got: {self.got_type.__name__}")
        else:
            lines.append(f"expected: {self.expected_type.__name__} (value: {self.expected_val_repr})")
            lines.append(f"got: {self.got_type.__name__} (value: {self.got_val_repr})")
        lines.append(f"suggested fix: {self.suggestion}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.__str__()

    def show(self):
        """Prints the comparison result in a beautiful CLI panel."""
        if not RICH_AVAILABLE:
            print(self.__str__())
            return
            
        console = Console(stderr=True)
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="cyan bold")
        table.add_column("Value", style="white")
        
        if self.is_type_only:
            table.add_row("expected:", self.expected_type.__name__)
            table.add_row("got:", Text(self.got_type.__name__, style="red"))
        else:
            table.add_row("expected:", f"{self.expected_type.__name__} ({self.expected_val_repr})")
            table.add_row("got:", Text(f"{self.got_type.__name__} ({self.got_val_repr})", style="red"))
            
        table.add_row("suggested fix:", Text(self.suggestion, style="green bold"))
        
        console.print(Panel(
            table,
            title="⚖️ Type / Value Comparison",
            title_align="left",
            border_style="yellow",
            padding=(1, 2)
        ))

    def _repr_html_(self) -> str:
        """HTML representation for Jupyter Notebooks."""
        exp_name = self.expected_type.__name__
        got_name = self.got_type.__name__
        
        exp_detail = f"<b>{exp_name}</b>"
        if not self.is_type_only:
            exp_detail += f" (value: <code>{self.expected_val_repr}</code>)"
            
        got_detail = f"<b style='color:#ef4444;'>{got_name}</b>"
        if not self.is_type_only:
            got_detail += f" (value: <code>{self.got_val_repr}</code>)"

        html = f"""
        <div style="
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-left: 6px solid #eab308;
            border-radius: 8px;
            padding: 16px;
            margin: 10px 0;
            max-width: 500px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        ">
            <div style="font-weight: bold; color: #854d0e; font-size: 1.05em; margin-bottom: 12px; display: flex; align-items: center;">
                <span style="margin-right: 6px;">⚖️</span> Type & Value Comparison
            </div>
            <table style="border: none; border-collapse: collapse; width: 100%; font-size: 0.95em;">
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="padding: 6px 0; color: #64748b; font-weight: 500;">Expected:</td>
                    <td style="padding: 6px 0; color: #1e293b;">{exp_detail}</td>
                </tr>
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="padding: 6px 0; color: #64748b; font-weight: 500;">Got:</td>
                    <td style="padding: 6px 0; color: #1e293b;">{got_detail}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #166534; font-weight: bold;">Suggested Fix:</td>
                    <td style="padding: 6px 0; color: #15803d; font-family: monospace; font-weight: bold;"><code>{self.suggestion}</code></td>
                </tr>
            </table>
        </div>
        """
        return html

def compare(expected: Any, got: Any, value: Any = None) -> ComparisonResult:
    """
    Compares expected types/values against got types/values,
    providing actionable conversion suggestions.
    
    Usage:
        pyerror.compare(int, str)
        pyerror.compare(int, "hello")
        pyerror.compare(expected=int, got=str, value="42")
    """
    result = ComparisonResult(expected, got, value)
    return result
