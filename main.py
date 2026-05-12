"""
main.py — RCA Agent CLI

Usage:
    python main.py                           # interactive prompt
    python main.py --log /var/log/app.log    # analyse a log file
    python main.py --text "payment svc down" # analyse text alert
    python main.py --file alert.txt          # read alert from file
"""

import argparse
import sys
import logging

logging.basicConfig(
    level=logging.WARNING,                   # suppress LangChain internals
    format="%(levelname)s %(name)s: %(message)s"
)

from agent import run_rca


def _print_banner():
    print("""
╔══════════════════════════════════════════════════════════╗
║          RCA Agent — Production Incident Analyser        ║
║  Sources: text alert | log file | JSON payload           ║
╚══════════════════════════════════════════════════════════╝
""")


def _run(input_str: str, source: str = None):
    print(f"\n🔍 Investigating...\n")
    result = run_rca(input_str, source_override=source)

    print("\n" + "═" * 64)
    print(result["rca_report"])
    print("═" * 64)
    print(f"\n  Steps taken : {result['steps_taken']}")
    print(f"  LLM         : {result['provider']}")
    if result.get("report_saved"):
        print(f"  Report saved: {result['report_saved']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="RCA Agent — Root Cause Analysis")
    parser.add_argument("--log",  help="Path to log file")
    parser.add_argument("--text", help="Incident text / alert message")
    parser.add_argument("--file", help="Path to text file containing the alert")
    args = parser.parse_args()

    _print_banner()

    if args.log:
        _run(args.log, source="log_file")

    elif args.text:
        _run(args.text, source="text_message")

    elif args.file:
        try:
            with open(args.file) as f:
                content = f.read().strip()
            _run(content)
        except FileNotFoundError:
            print(f"File not found: {args.file}")
            sys.exit(1)

    else:
        # Interactive mode
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

        _run(input_str)


if __name__ == "__main__":
    main()
