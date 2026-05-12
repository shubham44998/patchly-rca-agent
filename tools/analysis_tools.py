"""
tools/analysis_tools.py — Log & Metrics Analysis Tools

Deep analysis tools that run locally:
  - Log file analysis (errors, traces, anomaly patterns)
  - Metrics snapshot analysis (CPU, memory, latency thresholds)
  - Error pattern correlation across multiple logs
  - Timeline reconstruction
"""

import re
import json
from collections import Counter, defaultdict
from langchain.tools import tool


_EXCEPTION_RE  = re.compile(r"(\w+(?:Error|Exception|Fault|Panic))")
_TIMESTAMP_RE  = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})")
_HTTP_RE       = re.compile(r"\b(4\d{2}|5\d{2})\b")
_ERROR_KWS     = ["ERROR", "FATAL", "CRITICAL", "Exception", "Traceback", "panic:"]

# Metrics thresholds and their RCA implication
_METRIC_THRESHOLDS = {
    "cpu_pct":              (85,  "critical", "CPU saturation — runaway process or insufficient capacity"),
    "memory_pct":           (88,  "critical", "Memory pressure — OOM risk, GC thrashing, or leak"),
    "disk_pct":             (90,  "critical", "Disk full — writes failing, log rotation may have stopped"),
    "error_rate_pct":       (5,   "high",     "Elevated error rate — service degradation"),
    "latency_p99_ms":       (2000,"high",     "High tail latency — downstream bottleneck, DB slowness, or GC pause"),
    "latency_p50_ms":       (500, "medium",   "Elevated median latency — general slowness"),
    "connection_pool_pct":  (80,  "high",     "Connection pool saturation — DB or upstream throttling"),
    "thread_pool_pct":      (90,  "critical", "Thread pool exhausted — service unable to accept requests"),
    "gc_pause_ms":          (500, "high",     "Long GC pause — memory pressure or heap sizing issue"),
    "queue_depth":          (1000,"medium",   "Deep queue — consumers falling behind producers"),
    "open_file_descriptors":(80,  "high",     "High FD usage — file descriptor leak or limit too low"),
}


@tool
def analyze_log_file(log_path: str) -> str:
    """
    Deep analysis of a log file: error types, stack traces, error timeline, anomaly patterns.
    Input: absolute path to the log file.
    Returns: structured analysis with top errors, traces, and timeline.
    """
    try:
        with open(log_path, "r", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return f"File not found: {log_path}"
    except Exception as e:
        return f"Cannot read {log_path}: {e}"

    error_lines = [l.strip() for l in lines if any(kw in l for kw in _ERROR_KWS)]
    traces      = _extract_traces(lines)
    exc_counts  = Counter(m for l in error_lines for m in _EXCEPTION_RE.findall(l)).most_common(5)
    http_codes  = Counter(c for l in error_lines for c in _HTTP_RE.findall(l)).most_common()
    timeline    = _error_timeline(lines)
    ts_first, ts_last = _timestamp_range(lines)

    parts = [
        f"File         : {log_path}",
        f"Total lines  : {len(lines)}",
        f"Error lines  : {len(error_lines)}",
        f"Time range   : {ts_first or '?'} → {ts_last or '?'}",
        "",
    ]
    if exc_counts:
        parts += ["Exception types:"] + [f"  {e}: {c}×" for e, c in exc_counts] + [""]
    if http_codes:
        parts += ["HTTP error codes:"] + [f"  {c}: {n}×" for c, n in http_codes] + [""]
    if timeline:
        parts += ["Error rate per minute (recent):"] + [f"  {t}: {n}" for t, n in timeline[-10:]] + [""]
    if error_lines:
        parts += ["Recent errors (last 15):"] + [f"  {l}" for l in error_lines[-15:]] + [""]
    for i, tr in enumerate(traces[-3:], 1):
        parts += [f"Stack trace #{i}:", tr[:2000], ""]

    return "\n".join(parts)


@tool
def analyze_metrics(metrics_json: str) -> str:
    """
    Analyse a JSON metrics snapshot and flag anomalies with root-cause hypotheses.
    Input: JSON string, e.g.:
      '{"cpu_pct": 95, "memory_pct": 87, "latency_p99_ms": 3200, "error_rate_pct": 12}'
    Returns: anomaly report with severity and likely causes.
    """
    try:
        metrics = json.loads(metrics_json)
    except json.JSONDecodeError:
        return "Invalid JSON. Provide metrics as a JSON object."

    anomalies, normal = [], []
    for key, value in metrics.items():
        if key in _METRIC_THRESHOLDS:
            threshold, sev, implication = _METRIC_THRESHOLDS[key]
            if float(value) >= threshold:
                anomalies.append(
                    f"  [{sev.upper()}] {key} = {value} "
                    f"(threshold {threshold}) → {implication}"
                )
            else:
                normal.append(f"  ✓ {key} = {value}")
        else:
            normal.append(f"  ? {key} = {value}  (no threshold defined)")

    lines = ["=== Metrics Analysis ==="]
    if anomalies:
        lines += ["\nANOMALIES:"] + anomalies
    else:
        lines += ["\nNo anomalies detected."]
    lines += ["\nNormal:"] + normal
    return "\n".join(lines)


@tool
def correlate_errors_across_logs(log_paths_csv: str) -> str:
    """
    Compare error patterns across multiple log files to find common root causes.
    Input: comma-separated list of log file paths.
    Example: '/var/log/api/error.log,/var/log/db/postgres.log'
    Returns: per-file error summary + shared exception types across files.
    """
    paths   = [p.strip() for p in log_paths_csv.split(",") if p.strip()]
    results = {}
    all_exc = Counter()

    for path in paths:
        try:
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()
            errs  = [l.strip() for l in lines if any(kw in l for kw in _ERROR_KWS)]
            excs  = Counter(m for l in errs for m in _EXCEPTION_RE.findall(l))
            results[path] = {"errors": len(errs), "exceptions": excs}
            all_exc += excs
        except Exception as e:
            results[path] = {"error": str(e)}

    parts = ["=== Cross-Log Error Correlation ===\n"]
    for path, data in results.items():
        if "error" in data:
            parts.append(f"{path}: FAILED — {data['error']}")
        else:
            top = data["exceptions"].most_common(3)
            parts.append(f"{path}: {data['errors']} errors | top: {top}")

    shared = [(e, c) for e, c in all_exc.most_common(5) if c > 1]
    if shared:
        parts += ["", "Shared exceptions (appear in multiple logs):"]
        parts += [f"  {e}: {c}×" for e, c in shared]
        parts += ["", "→ Shared exceptions strongly suggest a common upstream root cause."]
    else:
        parts += ["", "No shared exception types — errors appear isolated to individual services."]

    return "\n".join(parts)


@tool
def reconstruct_timeline(log_paths_csv: str) -> str:
    """
    Build a chronological event timeline from one or more log files.
    Interleaves error events across services to show what happened first.
    Input: comma-separated log file paths.
    Returns: unified timeline of error events, sorted by timestamp.
    """
    paths  = [p.strip() for p in log_paths_csv.split(",") if p.strip()]
    events = []

    for path in paths:
        svc = path.split("/")[-1]
        try:
            with open(path, "r", errors="replace") as f:
                for line in f:
                    if any(kw in line for kw in _ERROR_KWS):
                        m = _TIMESTAMP_RE.search(line)
                        if m:
                            events.append((m.group(1), svc, line.strip()[:120]))
        except Exception:
            continue

    if not events:
        return "No timestamped error events found in provided logs."

    events.sort(key=lambda x: x[0])
    parts = [f"=== Unified Error Timeline ({len(events)} events) ===\n"]
    for ts, svc, msg in events[-40:]:   # last 40 events
        parts.append(f"  {ts}  [{svc}]  {msg}")
    return "\n".join(parts)


# ── Internal helpers ──────────────────────────────────────────

def _extract_traces(lines):
    traces, current = [], []
    for line in lines:
        s = line.strip()
        if "Traceback" in s or re.match(r"\s+at\s+\w", line):
            current.append(s) if current else [current := [s]]
        elif re.search(r"\w+(?:Error|Exception):", s) and not current:
            current = [s]
        elif current:
            if s:
                current.append(s)
            else:
                traces.append("\n".join(current))
                current = []
    if current:
        traces.append("\n".join(current))
    return traces


def _error_timeline(lines):
    counts = defaultdict(int)
    for l in lines:
        if any(kw in l for kw in ["ERROR", "FATAL", "CRITICAL"]):
            m = _TIMESTAMP_RE.search(l)
            if m:
                counts[m.group(1)[:16]] += 1
    return sorted(counts.items())


def _timestamp_range(lines):
    ts = [m.group(1) for l in lines for m in [_TIMESTAMP_RE.search(l)] if m]
    return (ts[0], ts[-1]) if ts else (None, None)
