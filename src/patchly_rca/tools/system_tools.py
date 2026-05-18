"""
tools/system_tools.py — System Diagnostic Tools

Runs shell commands for live system inspection:
  - Process state (ps, top)
  - Disk / memory (df, free)
  - Network (netstat, ss, curl)
  - Docker / Kubernetes
  - Git (recent commits, blame)
  - Database CLIs
  - Journal / systemctl logs

All commands are validated against the whitelist in config.
Destructive commands (rm, kill, etc.) are blocked unless explicitly enabled.
"""

import subprocess
import shlex
from langchain.tools import tool
from patchly_rca.config import SYSTEM_TOOLS


_DESTRUCTIVE = {"rm", "kill", "pkill", "killall", "shutdown", "reboot",
                "mkfs", "dd", "chmod", "chown", "passwd", "userdel"}


def _run(cmd: str) -> str:
    """Validate and execute a shell command, return stdout+stderr."""
    parts = shlex.split(cmd)
    if not parts:
        return "Empty command."

    binary = parts[0]

    if binary in _DESTRUCTIVE and not SYSTEM_TOOLS.get("allow_destructive"):
        return (f"Command '{binary}' is blocked (destructive). "
                "Set allow_destructive=True in config to enable.")

    allowed = SYSTEM_TOOLS.get("allowed_commands", [])
    if allowed and binary not in allowed:
        return (f"Command '{binary}' is not in the allowed_commands whitelist. "
                f"Allowed: {allowed}")

    timeout = SYSTEM_TOOLS.get("timeout_seconds", 15)
    try:
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            return f"[exit {result.returncode}]\n{err or out}"
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s: {cmd}"
    except FileNotFoundError:
        return f"Command not found: {binary}"
    except Exception as e:
        return f"Error running command: {e}"


# ── Individual tools ──────────────────────────────────────────

@tool
def run_shell_command(command: str) -> str:
    """
    Run a safe diagnostic shell command on the production host.
    Use for: ps aux, df -h, free -m, uptime, netstat -tlnp, ss -s, lsof -i, uname -a
    Input: the exact shell command to run.
    Returns: command stdout or error message.
    """
    return _run(command)


@tool
def check_process_state(service_name: str) -> str:
    """
    Check if a service/process is running and get its resource usage.
    Input: service or process name (e.g. 'nginx', 'postgres', 'payment-service').
    Returns: matching ps output + systemctl status if available.
    """
    ps_out    = _run(f"ps aux")
    lines     = [l for l in ps_out.splitlines() if service_name.lower() in l.lower()]
    ps_result = "\n".join(lines) if lines else f"No process matching '{service_name}' found."
    systemctl = _run(f"systemctl status {service_name} --no-pager -l")
    return f"=== ps output ===\n{ps_result}\n\n=== systemctl ===\n{systemctl}"


@tool
def check_disk_and_memory() -> str:
    """
    Check current disk usage and memory state on the host.
    Returns df -h and free -m output.
    """
    disk = _run("df -h")
    mem  = _run("free -m")
    load = _run("uptime")
    return f"=== Disk ===\n{disk}\n\n=== Memory ===\n{mem}\n\n=== Load ===\n{load}"


@tool
def check_network_connections(port: str = "") -> str:
    """
    Inspect active network connections, open ports, and socket state.
    Input: optional port number to filter by (e.g. '5432', '8080'). Leave empty for overview.
    Returns: ss or netstat output.
    """
    cmd = f"ss -tlnp" + (f" | grep {port}" if port else "")
    return _run(cmd)


@tool
def tail_log_file(log_path_and_lines: str) -> str:
    """
    Tail the end of a log file for the most recent entries.
    Input format: '/path/to/file.log' or '/path/to/file.log|200' (pipe-separated path and line count).
    Returns: last N lines of the log (default 100).
    """
    parts = log_path_and_lines.split("|")
    path  = parts[0].strip()
    n     = parts[1].strip() if len(parts) > 1 else "100"
    return _run(f"tail -n {n} {path}")


@tool
def grep_log(query: str) -> str:
    """
    Search a log file for a specific pattern, error, or keyword.
    Input format: 'keyword|/path/to/file.log' or 'keyword' to search /var/log/syslog.
    Example: 'OOMKilled|/var/log/app/error.log'
    Returns: matching lines with context (up to 50 results).
    """
    parts   = query.split("|")
    keyword = parts[0].strip()
    path    = parts[1].strip() if len(parts) > 1 else "/var/log/syslog"
    return _run(f"grep -n --color=never '{keyword}' {path} | head -50")


@tool
def check_docker_state(container_name: str = "") -> str:
    """
    Check Docker container status, recent logs, and resource usage.
    Input: container name or ID (optional — lists all if empty).
    Returns: docker ps + logs + stats for the container.
    """
    if container_name:
        ps_out   = _run(f"docker ps -a --filter name={container_name}")
        logs_out = _run(f"docker logs --tail 50 {container_name}")
        stats    = _run(f"docker stats --no-stream {container_name}")
        return f"=== docker ps ===\n{ps_out}\n\n=== logs ===\n{logs_out}\n\n=== stats ===\n{stats}"
    return _run("docker ps -a")


@tool
def check_kubernetes_state(namespace_or_pod: str = "default") -> str:
    """
    Check Kubernetes pod status, recent events, and logs.
    Input: namespace name, pod name, or 'namespace/pod' format.
    Returns: kubectl get pods + describe + recent events.
    """
    if "/" in namespace_or_pod:
        ns, pod = namespace_or_pod.split("/", 1)
        pods    = _run(f"kubectl get pods -n {ns} | grep {pod}")
        desc    = _run(f"kubectl describe pod {pod} -n {ns}")
        logs    = _run(f"kubectl logs {pod} -n {ns} --tail=50")
        return f"=== pods ===\n{pods}\n\n=== describe ===\n{desc}\n\n=== logs ===\n{logs}"
    ns     = namespace_or_pod
    pods   = _run(f"kubectl get pods -n {ns}")
    events = _run(f"kubectl get events -n {ns} --sort-by=.metadata.creationTimestamp | tail -20")
    return f"=== pods ===\n{pods}\n\n=== events ===\n{events}"


@tool
def check_git_history(repo_and_count: str = ".|10") -> str:
    """
    Fetch recent Git commits to correlate incidents with deployments.
    Input format: '/path/to/repo|N' — repo path pipe-separated with commit count (default: .|10).
    Example: '/srv/app|20'
    Returns: last N git log entries with author, timestamp, and message.
    """
    parts = repo_and_count.split("|")
    repo  = parts[0].strip() or "."
    n     = parts[1].strip() if len(parts) > 1 else "10"
    cmd   = f"git -C {repo} log --oneline --format='%h %ai %an — %s' -{n}"
    return _run(cmd)


@tool
def run_db_query(query: str) -> str:
    """
    Run a read-only diagnostic SQL query against a local database.
    Input format: 'db_type|connection|SQL'
    Examples:
      'psql|postgresql://user:pass@localhost/mydb|SELECT count(*) FROM pg_stat_activity WHERE state=\\'active\\''
      'mysql|mysql -u root mydb|SHOW PROCESSLIST'
    Returns: query result or error.
    WARNING: Only SELECT / SHOW / EXPLAIN queries are permitted.
    """
    parts = query.split("|", 2)
    if len(parts) < 3:
        return "Input must be: db_type|connection_string|SQL"

    db_type, conn, sql = parts[0].strip(), parts[1].strip(), parts[2].strip()

    sql_upper = sql.strip().upper()
    if not any(sql_upper.startswith(kw) for kw in ("SELECT", "SHOW", "EXPLAIN", "DESCRIBE")):
        return "Only SELECT / SHOW / EXPLAIN / DESCRIBE queries are allowed."

    if db_type.lower() == "psql":
        return _run(f'psql {conn} -c "{sql}"')
    elif db_type.lower() == "mysql":
        return _run(f'{conn} -e "{sql}"')
    else:
        return f"Unsupported db_type: {db_type}. Use 'psql' or 'mysql'."
