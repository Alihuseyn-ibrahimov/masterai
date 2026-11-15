"""Kassa agentləri: rəhbərin kompüterində.

    pip install -r requirements-agents.txt                 # hesabat (CrewAI)
    python -m kassa_agents.cli report --month 2026-11 --out kassa-2026-11.md

    pip install -r requirements-autogen.txt                # sual (AutoGen, AYRI venv)
    python -m kassa_agents.cli ask "Hansı qrupda borc ən çoxdur?"

Kassa xülasəsi mövcud `GET /live/kassa` ilə rəhbərin öz tokeni ilə alınır
(`MASTERAI_TOKEN` və ya `MASTERAI_EMAIL`/`_PASSWORD`, `MASTERAI_API`): serverdə yeni
icazə yolu yoxdur, agentlər heç nə YAZMIR.
"""

from __future__ import annotations

import argparse
import sys


def fetch_summary(client, month: str | None) -> dict:
    return client.call("GET", "/live/kassa", params={"month": month} if month else None)


def main(argv: list[str] | None = None, *, client=None, reporter=None, asker=None) -> int:
    parser = argparse.ArgumentParser(description="Kurs Kassası agentləri")
    sub = parser.add_subparsers(dest="command", required=True)
    p_report = sub.add_parser("report", help="aylıq hesabat (CrewAI)")
    p_report.add_argument("--month", help="YYYY-AA, defolt cari ay")
    p_report.add_argument("--out")
    p_ask = sub.add_parser("ask", help="Kassaya sual (AutoGen)")
    p_ask.add_argument("question")
    p_ask.add_argument("--month")
    p_ask.add_argument("--show-sql", action="store_true")
    args = parser.parse_args(argv)

    if client is None:
        from teacher_mcp.server import MasterAIClient
        client = MasterAIClient.from_env()
    summary = fetch_summary(client, args.month)

    if args.command == "report":
        if reporter is None:
            from kassa_agents.report_crew import monthly_report as reporter
        report = reporter(summary)
        print(report.markdown)
        if report.dropped:
            print(f"\n({len(report.dropped)} cümlə rəqəmi Kassada tapılmadığı üçün atıldı)", file=sys.stderr)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(report.markdown + "\n")
        return 0

    if asker is None:
        from kassa_agents.sql_team import ask, model_client_from_env

        def asker(question, data):
            return ask(question, data, analyst_client=model_client_from_env())
    answer = asker(args.question, summary)
    print(answer.text)
    if args.show_sql:
        for sql in answer.queries:
            print(f"-- {sql}", file=sys.stderr)
    return 0 if answer.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
