"""
main.py — Patchly RCA Agent entry point

CLI usage:
  python main.py                           # interactive prompt
  python main.py --log /var/log/app.log    # analyse a log file
  python main.py --text "payment svc down" # analyse text alert
  python main.py --file alert.txt          # read alert from file

Server usage:
  python main.py api        # start FastAPI on port 8000
  python main.py ui         # start Streamlit on port 8501
  python main.py both       # start both (API in background thread)
"""

import argparse
import sys
import subprocess
import threading
import logging

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s"
)

from patchly_rca.agent import run_rca


def _print_banner():
    print("""
╔══════════════════════════════════════════════════════════╗
║          RCA Agent — Production Incident Analyser        ║
║  Sources: text alert | log file | JSON payload           ║
╚══════════════════════════════════════════════════════════╝
""")


def _run_rca(input_str: str, source: str = None):
    print(f"\n🔍 Investigating...\n")
    result = run_rca(input_str, source_override=source)

    print("\n" + "═" * 64)
    print(result["rca_report"])
    print("═" * 64)
    print(f"\n  Steps taken : {result['steps_taken']}")
    print(f"  LLM         : {result['provider']}")
    
    token_usage = result.get("token_usage", {})
    if token_usage.get("total_tokens"):
        print(f"  Tokens      : {token_usage['total_tokens']} total "
              f"({token_usage['prompt_tokens']} prompt + {token_usage['completion_tokens']} completion)")
        print(f"  LLM calls   : {token_usage['llm_calls']}")
    
    if result.get("report_saved"):
        print(f"  Report saved: {result['report_saved']}")
    print()


def _start_api():
    subprocess.run([sys.executable, "-m", "uvicorn", "patchly_rca.api.main:app", "--reload", "--port", "8000"])


def _start_ui():
    subprocess.run([sys.executable, "-m", "streamlit", "run", "ui/app.py"])


def main():
    parser = argparse.ArgumentParser(description="Patchly RCA Agent")
    parser.add_argument("command", nargs="?", help="api | ui | both (starts servers)")
    parser.add_argument("--log",  help="Path to log file")
    parser.add_argument("--text", help="Incident text / alert message")
    parser.add_argument("--file", help="Path to text file containing the alert")
    args = parser.parse_args()

    # ── Server mode ───────────────────────────────────────────
    if args.command == "api":
        _start_api()
        return
    if args.command == "ui":
        _start_ui()
        return
    if args.command == "both":
        threading.Thread(target=_start_api, daemon=True).start()
        _start_ui()
        return

    # ── CLI / RCA mode ────────────────────────────────────────
    _print_banner()

    if args.log:
        _run_rca(args.log, source="log_file")

    elif args.text:
        _run_rca(args.text, source="text_message")

    elif args.file:
        try:
            with open(args.file) as f:
                content = f.read().strip()
            _run_rca(content)
        except FileNotFoundError:
            print(f"File not found: {args.file}")
            sys.exit(1)

    else:
        print("Enter your incident (log file path, alert text, or JSON payload).")
        print("Type END on a new line when done.\n")
        lines = []
        try:
            while True:
                line = input()
                if line.strip().upper() == "END":
                    break
                lines.append(line)
        except (EOFError, KeyboardInterrupt):
            pass

        input_str = "\n".join(lines).strip()
        if not input_str:
            print("No input provided. Exiting.")
            sys.exit(0)

        _run_rca(input_str)


if __name__ == "__main__":
    main()
