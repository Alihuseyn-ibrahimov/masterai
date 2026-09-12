#!/usr/bin/env python3
"""Təkrarlanmış canlı sessiya iştirakçılarını birləşdirir.

REAL HADİSƏ (2026-09-12, sessiya #31): tələbə səhifəni yeniləyəndə hər
dəfə YENİ `live_participants` sətri yaranırdı — bazada bir Amil üç
sətirlə göründü, balı üç yerə bölündü, özü də qayıdanda yenidən 0-cı
sualdan başladı. Kök səbəb `LiveSessionStore.add_participant`-də
düzəldildi (tap-və-ya-yarat), amma ARTIQ YARANMIŞ sətirlər bazada qalır.
Bu skript məhz onları təmizləyir.

NİYƏ AVTOMATİK MİQRASİYA DEYİL: bu, datanı BİRLƏŞDİRİR (cavabları
köçürür, sətirləri silir). Geri qaytarmaq yalnız backup-dan mümkündür,
ona görə servis start-ında sükutla işləməməlidir.

Qayda sadədir: (sessiya, istifadəçi) cütü üçün ƏN ERKƏN sətir qalır,
qalanların cavabları ona köçür. Eyni sual iki sətirdə cavablanıbsa,
İLK cavab saxlanılır. `user_id IS NULL` (köhnə anonim PIN) sətirlərə
TOXUNULMUR — kimin olduğu bilinmir.

İstifadə (VPS-də, MÜTLƏQ backup-dan sonra):

    python3 deploy/repair_duplicate_participants.py live_sessions.db
    python3 deploy/repair_duplicate_participants.py live_sessions.db --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys


def find_duplicates(conn: sqlite3.Connection) -> list[dict]:
    """(sessiya, istifadəçi) üzrə birdən çox sətri olan qruplar.

    `keep_id` — ən erkən qoşulma (bərabərlikdə ən kiçik `id`).
    `joined_at` mətn ISO-8601-dir, yəni leksik sıralama xronolojidir.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT session_id, user_id, id, joined_at FROM live_participants "
        "WHERE user_id IS NOT NULL ORDER BY session_id, user_id, joined_at, id"
    ).fetchall()

    groups: dict[tuple[int, int], list[int]] = {}
    for row in rows:
        groups.setdefault((row["session_id"], row["user_id"]), []).append(row["id"])

    return [
        {
            "session_id": session_id,
            "user_id": user_id,
            "keep_id": ids[0],
            "drop_ids": ids[1:],
        }
        for (session_id, user_id), ids in groups.items()
        if len(ids) > 1
    ]


def repair(conn: sqlite3.Connection, *, apply: bool) -> dict:
    """Birləşdirmə. `apply=False` heç nə yazmır, yalnız sayır."""
    conn.row_factory = sqlite3.Row
    groups = find_duplicates(conn)

    moved = 0
    dropped = 0
    removed = 0
    stale_reports: list[int] = []

    for group in groups:
        keep_id = group["keep_id"]
        session_id = group["session_id"]

        answered = {
            row["question_index"]
            for row in conn.execute(
                "SELECT question_index FROM live_answers "
                "WHERE session_id = ? AND participant_id = ?",
                (session_id, keep_id),
            ).fetchall()
        }

        for drop_id in group["drop_ids"]:
            extras = conn.execute(
                "SELECT id, question_index FROM live_answers "
                "WHERE session_id = ? AND participant_id = ? ORDER BY answered_at, id",
                (session_id, drop_id),
            ).fetchall()
            for answer in extras:
                if answer["question_index"] in answered:
                    dropped += 1
                    if apply:
                        conn.execute("DELETE FROM live_answers WHERE id = ?", (answer["id"],))
                    continue
                answered.add(answer["question_index"])
                moved += 1
                if apply:
                    conn.execute(
                        "UPDATE live_answers SET participant_id = ? WHERE id = ?",
                        (keep_id, answer["id"]),
                    )
            removed += 1
            if apply:
                conn.execute("DELETE FROM live_participants WHERE id = ?", (drop_id,))

        report = conn.execute(
            "SELECT report_json FROM live_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if report is not None and report["report_json"]:
            # Saxlanmış hesabat `participant_id` ilə yazılıb — sətirlər
            # birləşəndən sonra köhnəlir. Sükutla keçmək olmaz.
            if session_id not in stale_reports:
                stale_reports.append(session_id)

    if apply:
        conn.commit()

    return {
        "groups": len(groups),
        "removed_participants": removed,
        "moved_answers": moved,
        "dropped_answers": dropped,
        "stale_reports": stale_reports,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", help="live_sessions.db yolu")
    parser.add_argument(
        "--apply", action="store_true",
        help="dəyişiklikləri YAZ (defolt: yalnız göstər)",
    )
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    groups = find_duplicates(conn)
    if not groups:
        print("Təkrarlanmış iştirakçı YOXDUR — baza təmizdir.")
        return 0

    print(f"Təkrarlanmış qrup: {len(groups)}")
    for group in groups:
        name_row = conn.execute(
            "SELECT display_name FROM live_participants WHERE id = ?", (group["keep_id"],)
        ).fetchone()
        name = name_row["display_name"] if name_row else "?"
        print(
            f"  sessiya #{group['session_id']} · {name} (user_id={group['user_id']}): "
            f"{group['keep_id']} qalır, silinir {group['drop_ids']}"
        )

    summary = repair(conn, apply=args.apply)
    rejim = "YAZILDI" if args.apply else "QURU REJİM (heç nə yazılmadı)"
    print(
        f"\n{rejim}: {summary['removed_participants']} sətir silinir, "
        f"{summary['moved_answers']} cavab köçür, "
        f"{summary['dropped_answers']} təkrar cavab atılır."
    )
    if summary["stale_reports"]:
        print(
            "DİQQƏT — bu sessiyaların SAXLANMIŞ hesabatı köhnəlir "
            f"(iştirakçı ID-ləri dəyişdi): {summary['stale_reports']}"
        )
    if not args.apply:
        print("Yazmaq üçün: --apply (ƏVVƏLCƏ BACKUP AL)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
