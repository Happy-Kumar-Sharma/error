"""
pyerror.clustering — group "the same bug wearing different ids" together.

The analytics tracker (pyerror.analytics) keys records by an exact signature
"Type: message (@ file:line in func)", so `user 1234567 not found` and
`user 9876543 not found` show up as two separate rows. This module folds
those rows into clusters by normalizing away the volatile fragments
(hex addresses, uuids, long numbers, quoted paths) using THE SAME regex
table as pyerror.otel's fingerprint — imported, not copied, so grouping
stays consistent across the whole package.

Public API:
    cluster_errors(data=None) -> List[ErrorCluster]
        data defaults to pyerror.analytics.get_analytics().data.
        Clusters are sorted by total count, descending.

    show_clusters(data=None)
        Plain-text summary (a rich table when `rich` is installed).

Design notes:
- The cluster key is (type, normalized message, normalized location). Line
  numbers in the location are also normalized (":<line>") so the same bug
  still groups together after unrelated edits shift the file.
- Everything is defensive: malformed records are skipped, a broken analytics
  file yields [], and show_clusters never raises.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pyerror.otel import _NORMALIZE_PATTERNS

__all__ = ["cluster_errors", "show_clusters", "ErrorCluster"]

try:
    from rich.console import Console
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:  # pragma: no cover
    RICH_AVAILABLE = False

# Line numbers move when code is edited; they must not split a cluster.
_LINENO_RE = re.compile(r":\d+\b")


@dataclass
class ErrorCluster:
    """A group of analytics records that are the same underlying bug."""

    fingerprint: str
    count: int
    signatures: List[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    representative: Dict[str, Any] = field(default_factory=dict)


def _normalize(text: str) -> str:
    for pattern, replacement in _NORMALIZE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _cluster_key(record: Dict[str, Any]) -> str:
    exc_type = str(record.get("type", ""))
    message = _normalize(str(record.get("message", "")))
    location = _LINENO_RE.sub(":<line>", _normalize(str(record.get("location", ""))))
    return "|".join([exc_type, message[:300], location])


def cluster_errors(data: Optional[Dict[str, Dict[str, Any]]] = None) -> List[ErrorCluster]:
    """Cluster analytics records by normalized (type, message, location).

    `data` is a mapping of signature -> record, exactly the shape stored by
    pyerror.analytics (fields: count/first_seen/last_seen/location/type/
    message). Defaults to the live analytics data. Never raises.
    """
    try:
        if data is None:
            from pyerror.analytics import get_analytics

            data = get_analytics().data
        if not isinstance(data, dict):
            return []

        buckets: Dict[str, ErrorCluster] = {}
        best_count: Dict[str, int] = {}
        for signature, record in data.items():
            if not isinstance(record, dict):
                continue
            try:
                key = _cluster_key(record)
                count = int(record.get("count", 1))
                first_seen = str(record.get("first_seen", ""))
                last_seen = str(record.get("last_seen", ""))
            except Exception:
                continue

            cluster = buckets.get(key)
            if cluster is None:
                fingerprint = hashlib.sha1(
                    key.encode("utf-8", errors="replace")).hexdigest()[:16]
                cluster = ErrorCluster(
                    fingerprint=fingerprint,
                    count=0,
                    signatures=[],
                    first_seen=first_seen,
                    last_seen=last_seen,
                    representative=dict(record, signature=str(signature)),
                )
                buckets[key] = cluster
                best_count[key] = -1

            cluster.count += count
            cluster.signatures.append(str(signature))
            # ISO-8601 strings sort correctly as plain strings.
            if first_seen and (not cluster.first_seen or first_seen < cluster.first_seen):
                cluster.first_seen = first_seen
            if last_seen and last_seen > cluster.last_seen:
                cluster.last_seen = last_seen
            if count > best_count[key]:
                best_count[key] = count
                cluster.representative = dict(record, signature=str(signature))

        return sorted(buckets.values(), key=lambda c: -c.count)
    except Exception:
        return []


def show_clusters(data: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """Print a summary of error clusters. Never raises."""
    try:
        clusters = cluster_errors(data)
        if not clusters:
            print("No error clusters yet.")
            return

        if RICH_AVAILABLE:
            console = Console(stderr=True)
            table = Table(title="Error Clusters (similar errors grouped)",
                          header_style="bold magenta")
            table.add_column("Fingerprint", style="dim")
            table.add_column("Count", justify="right", style="green bold")
            table.add_column("Variants", justify="right")
            table.add_column("Representative", ratio=3)
            table.add_column("Last Seen", style="dim cyan")
            for cluster in clusters:
                rep = cluster.representative
                rep_text = "{}: {}".format(rep.get("type", "?"),
                                           str(rep.get("message", ""))[:80])
                table.add_row(cluster.fingerprint, str(cluster.count),
                              str(len(cluster.signatures)), rep_text,
                              cluster.last_seen)
            console.print(table)
            return

        lines = ["=== Error Clusters ===", ""]
        for cluster in clusters:
            rep = cluster.representative
            lines.append("[{}] {}: {}".format(
                cluster.fingerprint, rep.get("type", "?"),
                str(rep.get("message", ""))[:100]))
            lines.append("  count: {}  variants: {}".format(
                cluster.count, len(cluster.signatures)))
            lines.append("  first seen: {}  last seen: {}".format(
                cluster.first_seen, cluster.last_seen))
            lines.append("")
        print("\n".join(lines))
    except Exception:
        pass
