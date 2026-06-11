"""
ingestion/ingestion.py — Incident ingestion and normalisation.

Supports three source types (auto-detected):
  log_file      — absolute path to a log file
  text_message  — free-form alert text / Slack / SMS
  json_payload  — PagerDuty / webhook JSON string
"""

import json
import os
from dataclasses import dataclass, field


class IngestionError(Exception):
    pass


@dataclass
class Incident:
    id: str
    source: str
    raw: str
    summary: str
    metadata: dict = field(default_factory=dict)

    def to_agent_context(self) -> str:
        lines = [
            f"Incident ID : {self.id}",
            f"Source      : {self.source}",
            f"Summary     : {self.summary}",
        ]
        if self.metadata:
            for k, v in self.metadata.items():
                lines.append(f"{k:<12}: {v}")
        lines += ["", "Raw input:", self.raw[:3000]]
        return "\n".join(lines)


def _next_id(prefix: str, counter_file: str) -> str:
    try:
        n = int(open(counter_file).read().strip()) + 1 if os.path.exists(counter_file) else 1
        open(counter_file, "w").write(str(n))
    except OSError:
        n = 1
    return f"{prefix}-{n:04d}"


def ingest(identifier: str, cfg: dict) -> Incident:
    source = cfg.get("default_source", "auto")

    if source == "auto":
        if os.path.sep in identifier or identifier.startswith("/"):
            source = "log_file"
        else:
            try:
                json.loads(identifier)
                source = "json_payload"
            except (json.JSONDecodeError, ValueError):
                source = "text_message"

    if source == "log_file":
        if not os.path.exists(identifier):
            raise IngestionError(f"Log file not found: {identifier}")
        tail = cfg.get("log_file", {}).get("tail_lines", 3000)
        with open(identifier, "r", errors="replace") as f:
            lines = f.readlines()
        raw = "".join(lines[-tail:])
        return Incident(
            id=f"LOG-{os.path.basename(identifier)}",
            source="log_file",
            raw=raw,
            summary=f"Log file: {identifier} ({len(lines)} lines)",
            metadata={"path": identifier, "total_lines": len(lines)},
        )

    if source == "json_payload":
        try:
            data = json.loads(identifier)
        except json.JSONDecodeError as e:
            raise IngestionError(f"Invalid JSON payload: {e}")
        txt_cfg = cfg.get("text_message", {})
        inc_id  = _next_id(txt_cfg.get("id_prefix", "INC"), txt_cfg.get("counter_file", "/tmp/rca_txt_counter.txt"))
        
        # Extract structured context from common fields
        summary_parts = []
        metadata = {}
        
        # Build detailed summary from available fields
        if "error_type" in data or "error_message" in data:
            error_type = data.get("error_type", "Exception")
            error_msg = data.get("error_message", "")
            summary_parts.append(f"{error_type}: {error_msg}")
        
        if "service_name" in data:
            summary_parts.append(f"in {data['service_name']}")
            metadata["service"] = data["service_name"]
        
        if "method" in data:
            summary_parts.append(f"at {data['method']}")
            metadata["method"] = data["method"]
        
        if "endpoint" in data:
            metadata["endpoint"] = data["endpoint"]
        
        if "environment" in data:
            metadata["environment"] = data["environment"]
        
        # Extract other metadata
        for k, v in data.items():
            if k not in ("text", "summary", "message", "error_type", "error_message", 
                        "service_name", "method", "endpoint", "environment", "stack_trace"):
                metadata[k] = str(v)
        
        summary = " ".join(summary_parts) if summary_parts else (
            data.get("text") or data.get("summary") or data.get("message") or "JSON payload"
        )
        
        return Incident(
            id=inc_id,
            source="json_payload",
            raw=identifier,
            summary=summary,
            metadata=metadata,
        )

    # text_message
    txt_cfg = cfg.get("text_message", {})
    inc_id  = _next_id(txt_cfg.get("id_prefix", "TXT"), txt_cfg.get("counter_file", "/tmp/rca_txt_counter.txt"))
    return Incident(
        id=inc_id,
        source="text_message",
        raw=identifier,
        summary=identifier[:200],
    )
