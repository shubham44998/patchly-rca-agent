"""
config/settings.py — Central Configuration
Loads all settings from .env (or environment variables).
Swap LLM provider by changing LLM_PROVIDER in .env — nothing else changes.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM ───────────────────────────────────────────────────────
_provider = os.getenv("LLM_PROVIDER", "ollama").lower()

LLM = {
    "provider":    _provider,
    "model":       os.getenv("LLM_MODEL", "llama3"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.0")),
    "max_tokens":  int(os.getenv("LLM_MAX_TOKENS", "4096")),

    # Ollama
    "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),

    # OpenAI
    "api_key": os.getenv("OPENAI_API_KEY", ""),

    # Azure OpenAI
    "azure_endpoint":   os.getenv("AZURE_OPENAI_ENDPOINT", ""),
    "azure_key":        os.getenv("AZURE_OPENAI_KEY", ""),
    "deployment_name":  os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
    "api_version":      os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),

    # Anthropic
    "anthropic_key": os.getenv("ANTHROPIC_API_KEY", ""),

    # Google Gemini
    "gemini_key": os.getenv("GEMINI_API_KEY", ""),
}

# ── Ingestion ─────────────────────────────────────────────────
INGESTION = {
    "default_source": "auto",
    "text_message": {
        "id_prefix":    "TXT",
        "counter_file": os.path.join(os.getenv("RCA_OUTPUT_DIR", "./rca_reports"), ".txt_counter"),
    },
    "log_file": {
        "tail_lines":      3000,
        "max_trace_chars": 2000,
    },
}

# ── System Tools ──────────────────────────────────────────────
SYSTEM_TOOLS = {
    "allow_destructive": False,
    "timeout_seconds":   15,
    "allowed_commands": [
        "ps", "top", "df", "du", "free", "uptime", "uname",
        "netstat", "ss", "lsof", "curl", "ping",
        "docker", "kubectl",
        "git",
        "cat", "tail", "grep", "awk", "sed", "wc",
        "journalctl", "systemctl",
        "psql", "mysql", "mongosh",
        "python3",
    ],
}

# ── MCP Servers ───────────────────────────────────────────────
MCP_SERVERS = {
    "filesystem": {
        "enabled": False,
        "command": "npx",
        "args":    ["-y", "@modelcontextprotocol/server-filesystem", "/var/log", "/tmp"],
    },
    "github": {
        "enabled": bool(os.getenv("GITHUB_TOKEN")),
        "command": "npx",
        "args":    ["-y", "@modelcontextprotocol/server-github"],
        "env":     {"GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_TOKEN", "")},
    },
    "git": {
        "enabled": False,
        "command": "uvx",
        "args":    ["mcp-server-git", "--repository", os.getenv("REPO_PATH", ".")],
    },
}

# ── RCA Output ────────────────────────────────────────────────
RCA = {
    "max_investigation_steps": 15,
    "output_dir": os.getenv("RCA_OUTPUT_DIR", "./rca_reports"),
}

# ── API ───────────────────────────────────────────────────────
API = {
    "host": os.getenv("API_HOST", "0.0.0.0"),
    "port": int(os.getenv("API_PORT", "8000")),
}
