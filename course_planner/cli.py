"""Kurs planlayıcısı: planla → bax → cədvələ yaz (gün 18).

    pip install -r requirements-agents.txt
    python -m course_planner.cli plan --topic "Azərbaycan Konstitusiyası" --lessons 8 --out plan.json
    # plan.md-ni oxu, plan.json-u istəsən əl ilə düzəlt
    python -m course_planner.cli push plan.json --class-id 3 --start 2026-11-10 --weekdays 1,3 --time 18:00

`push` mövcud REST API-ni müəllimin tokeni ilə çağırır (`MASTERAI_TOKEN` və ya
`MASTERAI_EMAIL`/`MASTERAI_PASSWORD`, `MASTERAI_API`) - gün 11-in MCP serveri
kimi: server tərəfdə yeni icazə yolu yoxdur. Planlama və yazma QƏSDƏN ayrıdır:
müəllim AI-nın planını görmədən 8 dərs sinfin cədvəlinə düşməməlidir.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, time

from course_planner.models import CoursePlan, lesson_requests, plan_markdown, schedule_dates


def push(plan: CoursePlan, client, *, class_id: int, start: date, weekdays: list[int], at: time,
         duration_min: int = 90, mode: str = "online", tz: str = "Asia/Baku") -> list[dict]:
    requests = lesson_requests(plan, schedule_dates(start, len(plan.lessons), weekdays, at, tz),
                               duration_min=duration_min, mode=mode)
    return [client.call("POST", f"/chats/{class_id}/lessons", json=body) for body in requests]


def main(argv: list[str] | None = None, *, client=None, planner=None) -> int:
    parser = argparse.ArgumentParser(description="CrewAI kurs planlayıcısı")
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan", help="3 agentli komanda ilə plan qur")
    p_plan.add_argument("--topic", required=True)
    p_plan.add_argument("--lessons", type=int, default=8)
    p_plan.add_argument("--level", default="orta")
    p_plan.add_argument("--goal", default="dövlət qulluğu imtahanına hazırlıq")
    p_plan.add_argument("--out", default="plan.json")
    p_push = sub.add_parser("push", help="planı sinfin cədvəlinə yaz")
    p_push.add_argument("plan")
    p_push.add_argument("--class-id", type=int, required=True)
    p_push.add_argument("--start", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
    p_push.add_argument("--weekdays", default="1,3", help="1 = bazar ertəsi ... 7 = bazar")
    p_push.add_argument("--time", type=time.fromisoformat, default=time(18, 0))
    p_push.add_argument("--duration", type=int, default=90)
    p_push.add_argument("--mode", choices=["online", "offline"], default="online")
    args = parser.parse_args(argv)

    if args.command == "plan":
        if not 1 <= args.lessons <= 40:
            parser.error("--lessons 1-40 arası olmalıdır")
        if planner is None:
            from course_planner.crew import plan_course as planner
        plan = planner(args.topic, args.lessons, level=args.level, goal=args.goal)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(plan.model_dump(), fh, ensure_ascii=False, indent=2)
        md_path = args.out.rsplit(".", 1)[0] + ".md"
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(plan_markdown(plan))
        print(plan_markdown(plan))
        print(f"Plan: {args.out} · {md_path}. Bax, sonra: python -m course_planner.cli push {args.out} --class-id N ...")
        return 0

    with open(args.plan, encoding="utf-8") as fh:
        plan = CoursePlan.model_validate(json.load(fh))
    if client is None:
        from teacher_mcp.server import MasterAIClient
        client = MasterAIClient.from_env()
    weekdays = [int(d) for d in args.weekdays.split(",") if d.strip()]
    created = push(plan, client, class_id=args.class_id, start=args.start, weekdays=weekdays, at=args.time,
                   duration_min=args.duration, mode=args.mode)
    for lesson in created:
        print(f"#{lesson['id']} {lesson['starts_at']} {lesson['title']}")
    print(f"{len(created)} dərs sinfin cədvəlinə yazıldı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
