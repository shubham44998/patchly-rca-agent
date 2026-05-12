"""
agent/rca_agent.py — RCA Agent Orchestrator
Compatible with: langchain==0.2.16, langchain-core==0.2.38, langchain-ollama==0.1.3

Selects the right agent factory based on LLM provider:
  Ollama          → create_react_agent         (text-based ReAct, local prompt)
  OpenAI / others → create_tool_calling_agent  (native function calling)
"""

import os
import json
import logging
from datetime import datetime
from typing import Any

from langchain.agents import AgentExecutor, create_tool_calling_agent, create_react_agent
from langchain.memory import ConversationBufferMemory
from langchain.tools import tool

from config import LLM, INGESTION, SYSTEM_TOOLS, MCP_SERVERS, RCA
from agent.llm_factory import get_llm
from agent.prompt import build_prompt
from ingestion import ingest, Incident, IngestionError
from tools.system_tools import (
    run_shell_command, check_process_state, check_disk_and_memory,
    check_network_connections, tail_log_file, grep_log,
    check_docker_state, check_kubernetes_state,
    check_git_history, run_db_query,
)
from tools.analysis_tools import (
    analyze_log_file, analyze_metrics,
    correlate_errors_across_logs, reconstruct_timeline,
)
from mcp import load_mcp_tools  # noqa: E402 — optional, gracefully degrades

logger = logging.getLogger(__name__)

# ── Build LLM ─────────────────────────────────────────────────
llm      = get_llm(LLM)
provider = LLM["provider"].lower()
prompt   = build_prompt(provider)    # ReAct for ollama, tool-calling for others


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
    # Log & metrics analysis
    analyze_log_file,
    analyze_metrics,
    correlate_errors_across_logs,
    reconstruct_timeline,
    # System diagnostics
    run_shell_command,
    check_process_state,
    check_disk_and_memory,
    check_network_connections,
    tail_log_file,
    grep_log,
    check_docker_state,
    check_kubernetes_state,
    check_git_history,
    run_db_query,
]

_mcp_tools = load_mcp_tools(MCP_SERVERS)
ALL_TOOLS  = _CORE_TOOLS + _mcp_tools

logger.info(
    f"RCA Agent | provider={provider} | model={LLM.get('model')} | "
    f"tools={len(_CORE_TOOLS)} core + {len(_mcp_tools)} MCP"
)


# ── Pick the right agent factory ─────────────────────────────
# langchain 0.2.x:
#   create_react_agent        → works with ALL LLMs (text-based tool use)
#   create_tool_calling_agent → works with LLMs that support native function calling
#                               (OpenAI, Anthropic, Azure OpenAI, some Ollama models)
#
# For Ollama we use ReAct because not all local models support function calling reliably.
# For OpenAI / Anthropic we use tool-calling for better reliability and fewer tokens.

if provider == "ollama":
    # ReAct requires: input, tools, tool_names, agent_scratchpad
    _agent = create_react_agent(llm, ALL_TOOLS, prompt)
else:
    # Tool-calling requires: input, agent_scratchpad (+ optional chat_history)
    _agent = create_tool_calling_agent(llm, ALL_TOOLS, prompt)

_executor = AgentExecutor(
    agent=_agent,
    tools=ALL_TOOLS,
    memory=ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
    ),
    verbose=True,
    max_iterations=RCA.get("max_investigation_steps", 15),
    handle_parsing_errors=True,
    return_intermediate_steps=True,
    # Ollama can be slow — give it more time
    max_execution_time=300 if provider == "ollama" else 120,
)


# ── Output persistence ────────────────────────────────────────
def _report_to_text(report: Any) -> str:
    """Convert common LLM/LangChain output shapes into report text."""
    if report is None:
        return ""
    if isinstance(report, str):
        return report
    if isinstance(report, bytes):
        return report.decode("utf-8", errors="replace")

    content = getattr(report, "content", None)
    if content is not None:
        return _report_to_text(content)

    if isinstance(report, list):
        parts = []
        for item in report:
            if isinstance(item, dict):
                if "text" in item:
                    parts.append(_report_to_text(item["text"]))
                elif "content" in item:
                    parts.append(_report_to_text(item["content"]))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(_report_to_text(item))
        return "\n".join(part for part in parts if part)

    if isinstance(report, dict):
        if "text" in report:
            return _report_to_text(report["text"])
        if "content" in report:
            return _report_to_text(report["content"])
        if "output" in report:
            return _report_to_text(report["output"])
        return json.dumps(report, ensure_ascii=False, indent=2)

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
            rca_report:   str — full structured RCA report,
            steps_taken:  int — number of tool calls made,
            provider:     str — LLM used,
            report_saved: str — path to saved report file,
        }

    Examples:
        run_rca("/var/log/payment/error.log")
        run_rca("CRITICAL: payment-service down. DB pool exhausted.")
        run_rca('{"text": "API 503", "service": "checkout", "error_rate": "98%"}')
    """
    query = input_str
    if source_override:
        query = f"[source:{source_override}] {input_str}"

    result  = _executor.invoke({"input": query})
    report  = _report_to_text(result["output"])
    n_steps = len(result.get("intermediate_steps", []))
    saved   = _save_report(report)

    return {
        "rca_report":   report,
        "steps_taken":  n_steps,
        "provider":     f"{LLM['provider']}/{LLM.get('model', 'default')}",
        "report_saved": saved,
    }


def ingest_only(input_str: str) -> Incident:
    """Ingest an incident without running the agent. Useful for testing."""
    return ingest(input_str, INGESTION)
