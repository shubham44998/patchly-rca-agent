"""
agent/rca_agent.py — RCA Agent Orchestrator
Compatible with: langchain>=1.0, langchain-core>=1.0, langgraph>=1.0

Uses LangGraph's prebuilt ReAct agent (create_react_agent) which works
for ALL providers — Ollama, OpenAI, Anthropic, Azure OpenAI.
"""

import os
import json
import logging
from datetime import datetime
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from patchly_rca.config import LLM, INGESTION, MCP_SERVERS, RCA
from patchly_rca.agent.llm_factory import get_llm
from patchly_rca.agent.prompt import build_prompt
from patchly_rca.agent.token_tracker import TokenTracker
from patchly_rca.ingestion import ingest, Incident, IngestionError
from patchly_rca.tools.system_tools import (
    run_shell_command, check_process_state, check_disk_and_memory,
    check_network_connections, tail_log_file, grep_log,
    check_docker_state, check_kubernetes_state,
    check_git_history, run_db_query,
)
from patchly_rca.tools.analysis_tools import (
    analyze_log_file, analyze_metrics,
    correlate_errors_across_logs, reconstruct_timeline,
)
from patchly_rca.tools.stack_trace_analyzer import (
    analyze_stack_trace, extract_error_context,
)
from patchly_rca.mcp_loader import load_mcp_tools

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ── Build LLM + prompt ────────────────────────────────────────
_base_llm = get_llm(LLM)
provider = LLM["provider"].lower()
prompt   = build_prompt(provider)

# Wrap LLM with token tracking callback
_token_tracker = TokenTracker()
llm = _base_llm.with_config(callbacks=[_token_tracker])


# ── Ingestion tool ────────────────────────────────────────────
@tool
def ingest_incident(identifier: str) -> str:
    """
    Ingest and normalise an incident from any supported source.

    Accepts (auto-detected by format):
      • Log file path   : /var/log/app/error.log
      • Text alert      : free-form text, SMS body, Slack message
      • JSON payload    : PagerDuty / custom webhook JSON string

    Returns a structured incident context block ready for investigation.
    """
    try:
        incident: Incident = ingest(identifier, INGESTION)
        return incident.to_agent_context()
    except IngestionError as e:
        return f"Ingestion failed: {e}"
    except Exception as e:
        logger.exception("Unexpected ingestion error")
        return f"Unexpected ingestion error: {e}"


# ── All tools ─────────────────────────────────────────────────
_CORE_TOOLS = [
    ingest_incident,
    extract_error_context, analyze_stack_trace,  # New context extraction tools
    analyze_log_file, analyze_metrics,
    correlate_errors_across_logs, reconstruct_timeline,
    run_shell_command, check_process_state, check_disk_and_memory,
    check_network_connections, tail_log_file, grep_log,
    check_docker_state, check_kubernetes_state,
    check_git_history, run_db_query,
]

_mcp_tools = load_mcp_tools(MCP_SERVERS)
ALL_TOOLS  = _CORE_TOOLS + _mcp_tools

logger.info(
    f"RCA Agent | provider={provider} | model={LLM.get('model')} | "
    f"tools={len(_CORE_TOOLS)} core + {len(_mcp_tools)} MCP"
)

# ── Build LangGraph ReAct agent ───────────────────────────────
_agent = create_react_agent(
    model=llm,
    tools=ALL_TOOLS,
    prompt=prompt,
)


# ── Output persistence ────────────────────────────────────────
def _report_to_text(report: Any) -> str:
    """Convert common LLM/LangChain output shapes into report text."""
    if report is None:
        return "No report generated."
    if isinstance(report, str):
        return report
    if isinstance(report, bytes):
        return report.decode("utf-8", errors="replace")

    # Handle list of content blocks (Anthropic/Gemini format)
    if isinstance(report, list):
        text_parts = []
        for item in report:
            if isinstance(item, dict):
                if "text" in item:
                    text_parts.append(str(item["text"]))
                elif "content" in item:
                    extracted = _report_to_text(item["content"])
                    if extracted:
                        text_parts.append(extracted)
            elif hasattr(item, "content"):
                extracted = _report_to_text(item.content)
                if extracted:
                    text_parts.append(extracted)
            elif isinstance(item, str):
                text_parts.append(item)
        result = "\n".join(text_parts)
        if result:
            return result
    
    # Try to extract content attribute
    if hasattr(report, "content"):
        content = report.content
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            return _report_to_text(content)
        elif content:
            return str(content)
    
    # Try __dict__
    if hasattr(report, "__dict__") and "content" in report.__dict__:
        return _report_to_text(report.__dict__["content"])
    
    # Try kwargs
    if hasattr(report, "kwargs") and "content" in report.kwargs:
        return _report_to_text(report.kwargs["content"])
    
    if hasattr(report, "text"):
        return _report_to_text(report.text)

    if isinstance(report, dict):
        if "text" in report:
            return _report_to_text(report["text"])
        if "content" in report:
            return _report_to_text(report["content"])
        if "output" in report:
            return _report_to_text(report["output"])

    return str(report)


def _save_report(report: str) -> str:
    out_dir = RCA.get("output_dir", "/tmp/rca_reports")
    os.makedirs(out_dir, exist_ok=True)
    ts   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"rca_{ts}.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        return path
    except OSError:
        return ""


# ── Public API ────────────────────────────────────────────────
def run_rca(input_str: str, source_override: str = None) -> dict:
    """
    Run a full RCA investigation.

    Args:
        input_str:       Log file path, text alert, or JSON payload.
        source_override: Force ingestion source: "text_message" | "log_file"

    Returns:
        {
            rca_report:      str — full structured RCA report,
            steps_taken:     int — number of tool calls made,
            provider:        str — LLM used,
            report_saved:    str — path to saved report file,
            token_usage:     dict — token consumption statistics,
        }
    """
    query = input_str
    if source_override:
        query = f"[source:{source_override}] {input_str}"

    _token_tracker.reset()
    logger.info("[RCA] Starting investigation...")
    
    result = _agent.invoke(
        {"messages": [("human", query)]},
        config={"callbacks": [_token_tracker]}
    )
    messages = result.get("messages", [])
    
    if not messages:
        logger.warning("Agent returned no messages")
        report = "No output from agent - check logs for errors."
    else:
        last_msg = messages[-1]
        report = _report_to_text(last_msg)
        
        if not report or report.strip() == "":
            logger.warning(f"Failed to extract text from message type: {type(last_msg).__name__}")
            report = f"Agent completed but produced no text output. Message type: {type(last_msg).__name__}"
    
    n_steps  = sum(1 for m in messages if getattr(m, "type", "") == "tool")
    saved    = _save_report(report)

    return {
        "rca_report":   report,
        "steps_taken":  n_steps,
        "provider":     f"{LLM['provider']}/{LLM.get('model', 'default')}",
        "report_saved": saved,
        "token_usage":  _token_tracker.get_usage(),
    }


def ingest_only(input_str: str) -> Incident:
    """Ingest an incident without running the agent. Useful for testing."""
    return ingest(input_str, INGESTION)
