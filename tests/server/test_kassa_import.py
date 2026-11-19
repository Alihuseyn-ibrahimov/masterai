"""Kurs Kassası: CSV/Excel importu (`server/kassa_import.py`, `POST /live/kassa/import`)."""

from __future__ import annotations

import io
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from server import kassa_import as ki
from server.app import (
    app, get_chat_store, get_connection_manager, get_message_store,
    get_payment_store, get_token_secret, get_user_store,
)
from server.auth import create_token, verify_password
from server.chat_store import ChatStore
from server.connection_manager import ConnectionManager
from server.message_store import MessageStore
from server.payment_store import PaymentStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
HEADER = "qrup;şagird;email;aylıq məbləğ;qoşulma tarixi;ay;ödənilən;ödəniş tarixi;borc"


def _csv(*lines: str, header: str = HEADER) -> bytes:
    return ("\n".join([header, *lines]) + "\n").encode("utf-8")


def _xlsx(rows: list[list]) -> bytes:
    book = Workbook()
    for row in rows:
        book.active.append(row)
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


# ---------- dəyərlər ----------

@pytest.mark.parametrize("text,expected", [
    ("120", 120), ("120.00", 120), ("120,00", 120), ("1 200 AZN", 1200), ("₼ 90", 90), ("", None),
])
def test_parse_amount(text, expected):
    assert ki.parse_amount(text) == expected


@pytest.mark.parametrize("text", ["abc", "12.5", "-5", "999999"])
def test_parse_amount_rejects(text):
    with pytest.raises(ValueError):
        ki.parse_amount(text)


@pytest.mark.parametrize("text,expected", [
    ("2026-11", "2026-11"), ("2026-1", "2026-01"), ("11.2026", "2026-11"), ("2026-11-01", "2026-11"),
    ("Noyabr 2026", "2026-11"), ("dekabr 2025", "2025-12"), ("01.11.2026", "2026-11"), ("", None),
])
def test_parse_month(text, expected):
    assert ki.parse_month(text) == expected


@pytest.mark.parametrize("text", ["2026-13", "noyabır 2026", "sabah"])
def test_parse_month_rejects(text):
    with pytest.raises(ValueError):
        ki.parse_month(text)


def test_parse_date_formats():
    assert ki.parse_date("03.11.2026").isoformat() == "2026-11-03"
    assert ki.parse_date("2026-11-03 10:00:00").isoformat() == "2026-11-03"
    with pytest.raises(ValueError):
        ki.parse_date("31.02.2026")


@pytest.mark.parametrize("title,column", [
    ("Qrup", "qrup"), ("Şagird", "şagird"), ("Ad Soyad", "şagird"), ("AYLIQ_MƏBLƏĞ", "aylıq məbləğ"),
    ("Ayliq mebleg", "aylıq məbləğ"), ("Ödəniş tarixi", "ödəniş tarixi"), ("E-poçt", "email"),
    ("odenilen", "ödənilən"), ("bilinməyən", None),
])
def test_header_aliases(title, column):
    assert ki.normalize_header(title) == column


# ---------- faylın oxunması ----------

def test_csv_with_comma_delimiter_and_bom():
    data = "﻿qrup,şagird,aylıq məbləğ\nA,Aysel,120\n".encode("utf-8")
    cols, rows = ki.read_table("f.csv", data)
    assert cols == ["qrup", "şagird", "aylıq məbləğ"]
    assert rows == [(2, {"qrup": "A", "şagird": "Aysel", "aylıq məbləğ": "120"})]


def test_csv_in_windows_turkish_encoding():
    # Köhnə Excel CSV-ni Türk kodlaşdırması ilə saxlayır (orada «ş/ğ/ı» var, «ə» yox).
    raw = "qrup;şagird\nA;Ağa Işıq\n".encode("cp1254")
    _, rows = ki.read_table("f.csv", raw)
    assert rows[0][1]["şagird"] == "Ağa Işıq"


def test_xlsx_reads_real_dates_and_numbers_and_skips_blank_rows():
    data = _xlsx([
        [None], ["Qrup", "Şagird", "Aylıq məbləğ", "Ay", "Ödənilən", "Ödəniş tarixi"],
        ["A", "Aysel", 120, datetime(2026, 11, 1), 120.0, datetime(2026, 11, 3)],
        [None, None, None],
    ])
    cols, rows = ki.read_table("Kassa.XLSX", data)
    assert rows == [(3, {"qrup": "A", "şagird": "Aysel", "aylıq məbləğ": "120", "ay": "2026-11-01",
                         "ödənilən": "120", "ödəniş tarixi": "2026-11-03"})]
    parsed, errors = ki.validate_rows(rows)
    assert errors == [] and parsed[0].month == "2026-11"


@pytest.mark.parametrize("name,data,message", [
    ("f.csv", b"", "boşdur"),
    ("f.xls", b"x", ".xls"),
    ("f.pdf", b"x", "Yalnız .csv"),
    ("f.xlsx", b"not a zip", "Excel faylı açılmadı"),
    ("f.csv", "ad;məbləğ\nAysel;10\n".encode(), "Məcburi sütun tapılmadı: qrup"),
    ("f.csv", "qrup;şagird;foo\n".encode(), "data sətri yoxdur"),
    ("f.csv", "qrup;şagird;grup\nA;B;C\n".encode(), "iki dəfə"),
])
def test_file_level_errors(name, data, message):
    with pytest.raises(ki.ImportFileError, match=message):
        ki.read_table(name, data)


def test_unknown_headers_are_named_in_the_error():
    with pytest.raises(ki.ImportFileError, match="Tanınmayan başlıqlar: Sinfi"):
        ki.read_table("f.csv", "Sinfi;şagird\nA;B\n".encode())


def test_too_large_file():
    with pytest.raises(ki.ImportFileError, match="2 MB"):
        ki.read_table("f.csv", b"x" * (ki.MAX_FILE_BYTES + 1))


# ---------- sətir yoxlaması ----------

def _validate(*lines):
    _, raw = ki.read_table("f.csv", _csv(*lines))
    return ki.validate_rows(raw)


def test_row_errors_carry_row_number_and_column():
    rows, errors = _validate(
        "A;Aysel;;120;;2026-11;120;;",          # 2: düzgün
        ";Murad;;120;;;;;",                     # 3: qrup boş
        "A;Nigar;;12x;;2026-13;;;",             # 4: məbləğ + ay
        "A;Leyla;;120;;;100;;",                 # 5: ödəniş var, ay yox
        "A;Kamal;yanlis-email;120;;;;;",         # 6: email
        "A;Rauf;;0;;;;;",                        # 7: 0 məbləğ
    )
    assert [r.row for r in rows] == [2]
    got = {(e.row, e.column) for e in errors}
    assert got == {(3, "qrup"), (4, "aylıq məbləğ"), (4, "ay"), (5, "ay"), (6, "email"),
                   (7, "aylıq məbləğ")}
    assert any("12x" in e.message for e in errors)


# ---------- endpoint ----------

@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    payments = PaymentStore(":memory:")
    for dep, value in {
        get_user_store: users, get_chat_store: chats, get_payment_store: payments,
        get_message_store: MessageStore(":memory:"), get_connection_manager: ConnectionManager(),
        get_token_secret: _SECRET,
    }.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    course = users.courses.create("Master NR 1", "exam_prep", trial_days=30, seat_limit=30)
    other = users.courses.create("Başqa kurs", "exam_prep", trial_days=30, seat_limit=30)

    def person(email, name, *, teacher=False, admin=False, course_id=course["id"]):
        row = users.create(email, "h", name, course_id=course_id)
        users.set_teacher(row["id"], teacher)
        users.set_admin(row["id"], admin)
        return users.get_by_id(row["id"])

    boss = person("rehber@m.az", "Rəhbər", teacher=True, admin=True)
    teacher = person("muellim@m.az", "Müəllim", teacher=True)
    aysel = person("aysel@m.az", "Aysel Məmmədova")
    outsider = person("yad@b.az", "Yad", course_id=other["id"])
    chat = chats.create(kind="group", created_by=teacher["id"], name="Abituriyent A", course_id=course["id"])
    for u in (teacher, aysel):
        chats.add_member(chat["id"], u["id"])
    yield {"client": TestClient(app), "users": users, "chats": chats, "payments": payments,
           "course": course, "boss": boss, "teacher": teacher, "aysel": aysel, "chat": chat,
           "outsider": outsider}
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _post(env, data: bytes, *, apply=False, name="kassa.csv", user=None):
    return env["client"].post(
        "/live/kassa/import", headers=_auth(user or env["boss"]),
        files={"file": (name, data, "text/csv")}, data={"apply": "true" if apply else "false"})


def test_import_requires_course_admin(env):
    data = _csv("A;Aysel;;120;;;;;")
    assert env["client"].post("/live/kassa/import", files={"file": ("k.csv", data)}).status_code == 401
    assert _post(env, data, user=env["teacher"]).status_code == 403
    assert _post(env, data, user=env["aysel"]).status_code == 403


def test_file_error_is_400_with_clear_message(env):
    r = _post(env, b"x", name="kassa.xls")
    assert r.status_code == 400 and ".xlsx" in r.json()["detail"]


def test_preview_writes_nothing_then_apply_writes_everything(env):
    data = _csv(
        "Abituriyent A;Aysel Məmmədova;;120;;2026-09;120;03.09.2026;",
        "Abituriyent A;aysel  məmmədova;;120;;2026-10;60;;60",
        "Abituriyent A;Murad Əliyev;;120;;2026-10;;;120",
        "Magistratura B;Nigar Həsənova;nigar@m.az;150;2026-10-15;2026-11;150;;",
    )
    r = _post(env, data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is False and body["errors"] == [] and body["warnings"] == []
    assert body["groups_new"] == ["Magistratura B"] and body["groups_existing"] == ["Abituriyent A"]
    assert (body["students_new"], body["students_matched"]) == (2, 1)
    assert (body["fees"], body["payments"], body["paid_total"]) == (3, 3, 330)
    assert (body["unpaid_months"], body["debt_total"]) == (1, 180)  # Murad 120 + Ayselin qalığı 60
    assert len(env["chats"].list_ids_by_course(env["course"]["id"])) == 1  # heç nə yazılmayıb

    r = _post(env, data, apply=True)
    assert r.status_code == 200 and r.json()["applied"] is True

    chat_a = env["chat"]["id"]
    payments, chats, users = env["payments"], env["chats"], env["users"]
    aysel = env["aysel"]["id"]
    assert payments.list_fees_for_chat(chat_a)[aysel] == 120
    sept = payments.list_payments_for_chat(chat_a, "2026-09")[aysel]
    assert sept["amount"] == 120 and sept["paid_at"].startswith("2026-09-03")
    assert payments.list_payments_for_chat(chat_a, "2026-10")[aysel]["amount"] == 60
    # Mövcud üzv: qoşulma tarixi faylın ilk ayına çəkildi (yoxsa sentyabr borcu görünməzdi).
    assert chats.list_members_joined(chat_a)[aysel] == "2026-09-01T00:00:00+00:00"

    murad_id = next(uid for uid in chats.list_member_ids(chat_a)
                    if users.get_by_id(uid)["display_name"] == "Murad Əliyev")
    murad = users.get_by_id(murad_id)
    assert murad["email"].endswith("@kassa-import.invalid") and not murad["is_teacher"]
    assert not verify_password("", murad["password_hash"])  # şifrə ilə girmək olmur
    assert chats.list_members_joined(chat_a)[murad_id] == "2026-10-01T00:00:00+00:00"

    nigar = users.get_by_email("nigar@m.az")
    chat_b = next(c for c in chats.list_ids_by_course(env["course"]["id"]) if c != chat_a)
    assert chats.get(chat_b)["name"] == "Magistratura B"
    assert chats.list_members_joined(chat_b)[nigar["id"]] == "2026-10-15T00:00:00+00:00"

    # Kassa paneli importu görür: oktyabrda Murad borcludur, Ayselin qalığı 60.
    k = env["client"].get("/live/kassa", params={"month": "2026-10"}, headers=_auth(env["boss"])).json()
    debts = {d["display_name"]: d["amount"] for d in k["debtors"]}
    # Nigar 15 oktyabrda qoşulub (faylda yazılıb), oktyabr ödənişi faylda yoxdur.
    assert debts == {"Murad Əliyev": 120, "Aysel Məmmədova": 60, "Nigar Həsənova": 150}


def test_reimport_is_idempotent(env):
    data = _csv("Yeni qrup;Kamal Quliyev;;100;;2026-11;100;;")
    assert _post(env, data, apply=True).json()["students_new"] == 1
    again = _post(env, data, apply=True).json()
    assert again["applied"] and (again["students_new"], again["students_matched"]) == (0, 1)
    assert again["groups_new"] == [] and again["fees"] == 0
    assert len(env["chats"].list_ids_by_course(env["course"]["id"])) == 2


def test_apply_refuses_file_with_errors(env):
    r = _post(env, _csv("Yeni;Kamal;;100;;;;;", "Yeni;Rauf;;abc;;;;;"), apply=True).json()
    assert r["applied"] is False
    assert r["errors"] == [{"row": 3, "column": "aylıq məbləğ", "message": "«abc»: rəqəm deyil"}]
    assert len(env["chats"].list_ids_by_course(env["course"]["id"])) == 1


def test_cross_row_errors(env):
    r = _post(env, _csv(
        "A2;Aysel;;120;;2026-10;120;;",
        "A2;Aysel;;150;;2026-11;150;;",   # 3: məbləğ ziddiyyəti
        "A2;Murad;;100;;2026-10;100;;",
        "A2;Murad;;100;;2026-10;50;;",    # 5: eyni ay iki dəfə
        "A2;Nigar;;;;2026-10;80;;",       # 6: aylıq məbləğ yoxdur
    )).json()
    got = {(e["row"], e["column"]) for e in r["errors"]}
    assert got == {(3, "aylıq məbləğ"), (5, "ay"), (6, "aylıq məbləğ")}


def test_email_of_other_course_or_teacher_is_rejected(env):
    r = _post(env, _csv("A;Yad;yad@b.az;100;;;;;", "A;Müəllim;muellim@m.az;100;;;;;")).json()
    assert [(e["row"], e["message"]) for e in r["errors"]] == [
        (2, "bu email başqa kursun istifadəçisidir"), (3, "bu email müəllimindir, şagird deyil")]


def test_existing_student_matched_by_email_into_new_group(env):
    r = _post(env, _csv("Yay kursu;Aysel M.;AYSEL@m.az;90;;;;;"), apply=True).json()
    assert (r["students_new"], r["students_matched"]) == (0, 1)
    chat_ids = env["chats"].list_ids_by_course(env["course"]["id"])
    assert any(env["aysel"]["id"] in env["chats"].list_member_ids(c) and c != env["chat"]["id"]
               for c in chat_ids)


def test_ambiguous_name_in_group_needs_email(env):
    twin = env["users"].create("aysel2@m.az", "h", "Aysel Məmmədova", course_id=env["course"]["id"])
    env["chats"].add_member(env["chat"]["id"], twin["id"])
    r = _post(env, _csv("Abituriyent A;Aysel Məmmədova;;120;;;;;")).json()
    assert r["errors"][0]["column"] == "şagird" and "email" in r["errors"][0]["message"]
    ok = _post(env, _csv("Abituriyent A;Aysel Məmmədova;aysel2@m.az;120;;;;;")).json()
    assert ok["errors"] == [] and ok["students_matched"] == 1


def test_warnings_for_debt_mismatch_overpay_and_paid_in_db(env):
    env["payments"].set_fee(env["chat"]["id"], env["aysel"]["id"], 120)
    env["payments"].mark_paid(env["chat"]["id"], env["aysel"]["id"], "2026-11", 120, marked_by=env["boss"]["id"])
    r = _post(env, _csv(
        "Abituriyent A;Aysel Məmmədova;;;;2026-11;;;",   # bazada ödənib, faylda yox
        "Abituriyent A;Aysel Məmmədova;;;;2026-10;150;;",  # artıq ödəniş
        "Abituriyent A;Aysel Məmmədova;;;;2026-09;100;;10",  # borc 20 olmalı idi
    ), apply=True).json()
    assert r["applied"] is True and r["fees"] == 0
    assert {(w["row"], w["column"]) for w in r["warnings"]} == {(2, "ödənilən"), (3, "ödənilən"), (4, "borc")}
    # Bazadakı ödəniş silinmədi.
    assert env["payments"].list_payments_for_chat(env["chat"]["id"], "2026-11")[env["aysel"]["id"]]["amount"] == 120


def test_seat_limit_is_checked_before_writing(env):
    env["users"].courses.update_settings(env["course"]["id"], seat_limit=2)
    r = _post(env, _csv("B;Bir;;100;;;;;", "B;İki;;100;;;;;"), apply=True).json()
    assert r["applied"] is False
    assert r["errors"][0]["row"] == 0 and "yer limitində 1 boş yer" in r["errors"][0]["message"]


def test_xlsx_upload_end_to_end(env):
    data = _xlsx([["Qrup", "Şagird", "Aylıq məbləğ", "Ay", "Ödənilən"],
                  ["Abituriyent A", "Aysel Məmmədova", 120, datetime(2026, 11, 1), 120]])
    r = _post(env, data, name="kassa.xlsx", apply=True).json()
    assert r["applied"] and r["payments"] == 1


# ---------- şablon ----------

@pytest.mark.parametrize("ext", ["csv", "xlsx"])
def test_static_templates_are_current_and_import_cleanly(ext, env):
    path = f"{ki.TEMPLATE_DIR}/{ki.TEMPLATE_NAME}.{ext}"
    data = open(path, "rb").read()
    if ext == "csv":
        assert data.decode("utf-8") == ki.template_csv(), "python -m server.kassa_import ilə yenilə"
    else:
        sheet = load_workbook(io.BytesIO(data)).active
        expected = load_workbook(io.BytesIO(ki.template_xlsx())).active
        assert list(sheet.values) == list(expected.values), "python -m server.kassa_import ilə yenilə"
    r = _post(env, data, name=f"sablon.{ext}").json()
    assert r["errors"] == [] and r["warnings"] == [] and r["rows"] == len(ki.TEMPLATE_ROWS)
