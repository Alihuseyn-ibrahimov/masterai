"""Hücum yoxlaması — İŞLƏYƏN serverə qarşı (spec 2026-09-29, Faza 9).

pytest hər qoruyucunu ayrıca, yaddaşda sübut edir. Bu skript isə HƏQİQİ
prosesə (lokalda uvicorn, produksiyada nginx + uvicorn) HTTP/WS ilə, tələbənin
edə biləcəyi kimi hücum edir: başqa kursun çatı, bankı, dostluğu; sahib
paneli; saxta token; bağlı kurs; dolu kurs; təkrar dəvət; parol sınağı.

REJİMLƏR

  public — PRODUKSİYA üçün. Anonimdir, heç bir hesab YARATMIR:
      python deploy/diagnostics/attack_check.py public \\
          --base https://masterai.prdostu.com --api https://api.masterai.prdostu.com \\
          --direct http://<SERVER_IP>:8110
    Əvvəlcə yeni versiyanın canlı olduğunu yoxlayır (`/me/course` -> 401).
    Köhnə versiyada qeydiyyat AÇIQDIR, yəni kodsuz qeydiyyat sınağı real hesab
    yaradardı — ona görə preflight keçməsə skript dayanır.

  seed + full — YALNIZ LOKAL, boş müvəqqəti bazalarla (produksiyada İŞLƏTMƏ):
      export USERS_DB_PATH=/tmp/x/users.db CHATS_DB_PATH=/tmp/x/chats.db \\
             QUESTION_SETS_DB_PATH=/tmp/x/question_sets.db
      SEED=$(python deploy/diagnostics/attack_check.py seed)
      uvicorn server.app:app --port 8125 &
      python deploy/diagnostics/attack_check.py full --base http://127.0.0.1:8125 --seed "$SEED"

Çıxış kodu: 0 — hamısı keçdi, 1 — ən azı bir hücum UĞURLU oldu (deploy ETMƏ).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PASSWORD = "Parol1234"
# Mövcud olmayan, amma e-poçt validatorundan keçən ünvan (xüsusi domenlər
# `.test`/`.invalid` rədd olunur). Parol sınağı yalnız bu açarı bloklayır.
PROBE_EMAIL = "hucum-yoxlama@masterai-yoxlama.az"
LOGIN_LIMIT = 10  # server/app.py: login_rate_limiter (10 səhv / 15 dəq)


# --------------------------------------------------------------------- HTTP


def _request(url: str, method: str = "GET", token: str | None = None,
             body: dict | None = None, headers: dict | None = None) -> tuple[int, str, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        # Yönləndirməyə GETMİRİK — http->https yoxlaması 301-i özü görməlidir.
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(req, timeout=15) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8", "replace")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


class Checker:
    def __init__(self) -> None:
        self.failures = 0
        self.passed = 0

    def check(self, passed: bool, text: str, detail: str = "") -> bool:
        if passed:
            self.passed += 1
            print(f"OK   {text}")
        else:
            self.failures += 1
            print(f"XƏTA {text}" + (f"  [{detail}]" if detail else ""))
        return passed

    def expect(self, text: str, url: str, status: int | set[int], *, backend: bool = True,
               **kwargs) -> tuple[int, str]:
        """`backend=True`: cavab FastAPI-dən gəlməlidir (JSON). nginx-in öz 404
        HTML səhifəsi «qoruyucu işlədi» kimi SƏHV oxunmasın deyə."""
        code, ctype, text_body = _request(url, **kwargs)
        wanted = status if isinstance(status, set) else {status}
        ok = code in wanted and (not backend or "application/json" in ctype)
        self.check(ok, text, f"{code} {ctype} {text_body[:120]}")
        return code, text_body


def _forged_tokens(real_token: str | None, victim_id: int) -> dict[str, str]:
    def b64(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    tokens = {
        "alg=none": f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': str(victim_id)})}.",
    }
    try:
        import jwt

        tokens["başqa açarla imzalanmış"] = jwt.encode(
            {"sub": str(victim_id)}, "x" * 40, algorithm="HS256")
    except ImportError:
        pass
    if real_token:
        # Həqiqi tokenin imzası saxlanır, yalnız `sub` dəyişdirilir.
        header, _payload, signature = real_token.split(".")
        tokens["imzası saxlanıb, sub dəyişdirilib"] = f"{header}.{b64({'sub': str(victim_id)})}.{signature}"
    return tokens


def _ws_close_code(base: str, path: str, token: str) -> int | str:
    try:
        from websockets.exceptions import ConnectionClosed
        from websockets.sync.client import connect
    except ImportError:
        return "websockets kitabxanası yoxdur"
    url = base.replace("https://", "wss://").replace("http://", "ws://") + f"{path}?token={token}"
    try:
        with connect(url, open_timeout=10) as ws:
            while True:
                ws.recv(timeout=10)
    except ConnectionClosed as exc:
        return exc.rcvd.code if exc.rcvd else "kodsuz bağlandı"
    except TimeoutError:
        return "bağlanmadı (açıq qaldı)"


# ------------------------------------------------------------ ANONİM YOXLAMA


def anonymous_checks(c: Checker, base: str) -> bool:
    """Qaytarır: yeni versiya canlıdırmı (qeydiyyat sınaqları təhlükəsizdirmi)."""
    code, _ = c.expect("anonim /me/course -> 401 (yeni versiya + nginx `me` marşrutu)",
                       f"{base}/me/course", 401)
    if code != 401:
        print("\n     DAYANDIM: yeni versiya canlı deyil və ya nginx `me`-ni backend-ə ötürmür.\n"
              "     Köhnə versiyada qeydiyyat açıqdır - qeydiyyat sınağı real hesab yaradardı.")
        return False
    c.expect("anonim /owner/courses -> 401 (nginx `owner` marşrutu backend-ə çatır)",
             f"{base}/owner/courses", 401)
    c.expect("kodsuz qeydiyyat -> 422", f"{base}/auth/register", 422, method="POST",
             body={"email": PROBE_EMAIL, "password": PASSWORD, "display_name": "Yoxlama"})
    c.expect("səhv kurs kodu ilə qeydiyyat -> 404", f"{base}/auth/register", 404, method="POST",
             body={"email": PROBE_EMAIL, "password": PASSWORD, "display_name": "Yoxlama",
                   "course_code": "YOXDUR-0000"})
    c.expect("saxta dəvətlə müəllim qeydiyyatı -> 404", f"{base}/auth/register", 404, method="POST",
             body={"email": PROBE_EMAIL, "password": PASSWORD, "display_name": "Yoxlama",
                   "invite_token": "saxta-devet-tokeni-" + "x" * 20})
    c.expect("/admin/stats açarsız -> 403", f"{base}/admin/stats", 403)
    c.expect("/admin/stats səhv açarla -> 403", f"{base}/admin/stats", 403,
             headers={"X-Admin-Key": "sehv-acar"})
    for name, token in _forged_tokens(None, victim_id=1).items():
        c.expect(f"saxta token ({name}) -> 401", f"{base}/me/course", 401, token=token)
    return True


def public_checks(c: Checker, base: str, api: str | None, direct: str | None = None) -> None:
    if direct:
        # Backend yalnız 127.0.0.1-də dinləməlidir. Kənardan çatılırsa nginx
        # yan keçilir: saxta X-Real-IP ilə parol limiti də, marşrut siyahısı da işləmir.
        try:
            code, _, _ = _request(f"{direct.rstrip('/')}/health")
            c.check(False, f"backend kənardan BİRBAŞA açılmır ({direct})", f"cavab verdi: {code}")
        except (urllib.error.URLError, OSError):
            c.check(True, f"backend kənardan BİRBAŞA açılmır ({direct})")
    if not anonymous_checks(c, base):
        return
    for host in filter(None, (base, api)):
        for path in ("/openapi.json", "/docs", "/redoc"):
            code, _, _ = _request(f"{host}{path}")
            c.check(code == 404, f"{host}{path} bağlıdır (API xəritəsi açıq deyil)", str(code))
    for path in ("/.env", "/.git/config", "/users.db", "/data/users.db", "/server/app.py", "/agent.py"):
        code, _, _ = _request(f"{base}{path}")
        c.check(code in (403, 404), f"{path} verilmir", str(code))
    if base.startswith("https://"):
        code, _, _ = _request(base.replace("https://", "http://", 1) + "/")
        c.check(code in (301, 308), "http -> https yönləndirilir", str(code))

    # nginx `X-Real-IP`-ni ÖZÜ yazır. Hücumçu başlığı hər dəfə dəyişsə belə
    # limit onu tutmalıdır — tutmursa, parol sınağı limitsizdir.
    for attempt in range(LOGIN_LIMIT):
        _request(f"{base}/auth/login", method="POST",
                 body={"email": PROBE_EMAIL, "password": f"sehv{attempt}"},
                 headers={"X-Real-IP": f"10.0.0.{attempt + 1}"})
    c.expect(f"{LOGIN_LIMIT} səhv girişdən sonra saxta X-Real-IP ilə də -> 429",
             f"{base}/auth/login", 429, method="POST",
             body={"email": PROBE_EMAIL, "password": "sehv"}, headers={"X-Real-IP": "10.9.9.9"})


# --------------------------------------------------------------- LOKAL: SEED


def _seed() -> dict:
    from pipeline.models import MCQQuestion
    from server.auth import hash_password
    from server.chat_store import ChatStore
    from server.question_set_store import QuestionSetStore
    from server.user_store import UserStore

    users_path = os.environ["USERS_DB_PATH"]
    if users_path.startswith("/opt/") or Path(users_path).exists():
        raise SystemExit("seed yalnız BOŞ lokal baza üçündür (produksiya bazasına yazılmır)")
    users = UserStore(users_path)
    chats = ChatStore(os.environ["CHATS_DB_PATH"])
    banks = QuestionSetStore(os.environ["QUESTION_SETS_DB_PATH"])
    pw = hash_password(PASSWORD)

    def person(email: str, course_id: int, teacher: bool = False) -> dict:
        user = users.create(email, pw, email.split("@")[0], course_id=course_id)
        if teacher:
            users.set_teacher(user["id"], True)
        return user

    owner = person("sahib@hucum.az", 1, teacher=True)
    users.set_platform_owner(owner["id"], True)
    course_a = users.courses.create("Kurs A", "english", trial_days=30, seat_limit=30)
    course_b = users.courses.create("Kurs B", "english", trial_days=30, seat_limit=1)
    course_c = users.courses.create("Kurs C", "english", trial_days=30, seat_limit=30)
    teacher_a = person("muellim-a@hucum.az", course_a["id"], teacher=True)
    users.set_admin(teacher_a["id"], True)
    student_a = person("telebe-a@hucum.az", course_a["id"])
    removed = person("cixarilan@hucum.az", course_a["id"])
    users.set_active(removed["id"], False)
    teacher_b = person("muellim-b@hucum.az", course_b["id"], teacher=True)
    student_b = person("telebe-b@hucum.az", course_b["id"])  # kurs B dolur (1 yer)
    student_c = person("telebe-c@hucum.az", course_c["id"])

    chat_a = chats.create(kind="group", created_by=teacher_a["id"], name="A sinfi",
                          course_id=course_a["id"])
    for member in (teacher_a, student_a):
        chats.add_member(chat_a["id"], member["id"])
    chat_c = chats.create(kind="group", created_by=student_c["id"], name="C sinfi",
                          course_id=course_c["id"])
    chats.add_member(chat_c["id"], student_c["id"])

    bank_a = banks.create("xarici_dil", "A bankı", "link", "https://x", created_by=teacher_a["id"],
                          course_id=course_a["id"], profile="english", bank_kind="practice")
    banks.add_question(bank_a["id"], MCQQuestion(
        question="She ___ to school.", options=["goes", "go", "going", "gone", "went"],
        correct_index=0, explanation="He/She/It ilə fel -s alır."))
    banks.mark_ready(bank_a["id"])

    return {
        "password": PASSWORD,
        "owner": owner["email"], "owner_id": owner["id"],
        "teacher_a": teacher_a["email"], "student_a": student_a["email"],
        "student_a_id": student_a["id"], "removed": removed["email"],
        "teacher_b": teacher_b["email"], "student_b": student_b["email"],
        "student_b_id": student_b["id"], "student_c": student_c["email"],
        "course_b_code": course_b["join_code"], "course_c_id": course_c["id"],
        "chat_a": chat_a["id"], "chat_a_code": chat_a["invite_code"], "chat_c": chat_c["id"],
        "bank_a": bank_a["id"],
        "invite_a": users.courses.create_teacher_invite(course_a["id"], created_by=owner["id"]),
    }


# --------------------------------------------------------------- LOKAL: FULL


def full_checks(c: Checker, base: str, s: dict) -> None:
    anonymous_checks(c, base)

    def login(email: str) -> str:
        code, _, text = _request(f"{base}/auth/login", method="POST",
                                 body={"email": email, "password": s["password"]})
        if code != 200:
            raise SystemExit(f"{email} daxil ola bilmədi: {code} {text[:200]}")
        return json.loads(text)["token"]

    owner, teacher_a, student_a = login(s["owner"]), login(s["teacher_a"]), login(s["student_a"])
    teacher_b, student_b, student_c = login(s["teacher_b"]), login(s["student_b"]), login(s["student_c"])

    print("\n-- kurs sərhədi (B kursu A-ya hücum edir)")
    chat_a, bank_a = s["chat_a"], s["bank_a"]
    c.expect("B tələbəsi A çatının üzvlərini görmür -> 404",
             f"{base}/chats/{chat_a}/members", 404, token=student_b)
    c.expect("B tələbəsi A çatının reytinqini görmür -> 404",
             f"{base}/chats/{chat_a}/leaderboard", 404, token=student_b)
    code = _ws_close_code(base, f"/ws/chat/{chat_a}", student_b)
    c.check(code == 4404, "B tələbəsi A çatına WebSocket ilə qoşula bilmir (4404)", str(code))
    c.expect("B müəllimi A bankını açmır -> 404",
             f"{base}/live/question-sets/{bank_a}", 404, token=teacher_b)
    c.expect("B müəllimi A bankının suallarını görmür -> 404",
             f"{base}/live/question-sets/{bank_a}/questions", 404, token=teacher_b)
    c.expect("B müəllimi A bankının keyfiyyət hesabatını görmür -> 404",
             f"{base}/live/question-sets/{bank_a}/quality", 404, token=teacher_b)
    c.expect("B müəllimi A çatına kodla qoşula bilmir -> 404",
             f"{base}/chats/join-requests", 404, method="POST", token=teacher_b,
             body={"code": s["chat_a_code"]})
    c.expect("B tələbəsi A tələbəsinə dostluq göndərə bilmir -> 404",
             f"{base}/friends/requests", 404, method="POST", token=student_b,
             body={"addressee_user_id": s["student_a_id"]})
    c.expect("B müəllimi A tələbəsinin tarixçəsini görmür -> 404",
             f"{base}/history/student/{s['student_a_id']}", 404, token=teacher_b)
    lst_code, _, lst = _request(f"{base}/live/question-sets", token=teacher_b)
    c.check(lst_code == 200 and all(q["id"] != bank_a for q in json.loads(lst)),
            "B müəlliminin bank siyahısında A bankı yoxdur", f"{lst_code} {lst[:120]}")

    print("\n-- rol və sahib paneli")
    c.expect("tələbə müəllim endpoint-inə -> 403", f"{base}/live/question-sets", 403, token=student_a)
    c.expect("tələbə sahib panelinə -> 404", f"{base}/owner/courses", 404, token=student_a)
    c.expect("admin-müəllim sahib panelinə -> 404", f"{base}/owner/courses", 404,
             token=teacher_a)
    c.expect("sahib öz panelinə -> 200", f"{base}/owner/courses", 200, token=owner)
    c.expect("tələbə özünü müəllim edə bilmir (admin endpoint) -> 403",
             f"{base}/admin/teachers", 403, method="POST", token=student_a,
             body={"email": s["student_a"], "is_teacher": True})
    for name, token in _forged_tokens(student_a, victim_id=s["owner_id"]).items():
        c.expect(f"sahib adına saxta token ({name}) -> 401", f"{base}/owner/courses", 401, token=token)

    print("\n-- qeydiyyat")
    c.expect("dolu kursa (B, 1 yer) qeydiyyat -> 409", f"{base}/auth/register", 409, method="POST",
             body={"email": "artiq@hucum.az", "password": PASSWORD, "display_name": "Artıq",
                   "course_code": s["course_b_code"]})
    body = {"email": "yeni-muellim@hucum.az", "password": PASSWORD, "display_name": "Yeni",
            "invite_token": s["invite_a"]}
    c.expect("dəvətlə müəllim qeydiyyatı -> 201", f"{base}/auth/register", 201,
             method="POST", body=body)
    c.expect("EYNİ dəvətlə ikinci qeydiyyat -> 404", f"{base}/auth/register", 404, method="POST",
             body={**body, "email": "ikinci@hucum.az"})
    c.expect("kursdan çıxarılmış istifadəçi daxil ola bilmir -> 401", f"{base}/auth/login", 401,
             method="POST", body={"email": s["removed"], "password": s["password"]})

    print("\n-- lisenziya bağlananda")
    c.expect("sahib C kursunu dayandırır -> 200",
             f"{base}/owner/courses/{s['course_c_id']}/suspend", 200, method="POST", token=owner)
    c.expect("bağlı kursun KÖHNƏ tokeni ilə API -> 402", f"{base}/chats", 402, token=student_c)
    code = _ws_close_code(base, f"/ws/chat/{s['chat_c']}", student_c)
    c.check(code == 4402, "bağlı kursun tələbəsi çata WebSocket ilə girə bilmir (4402)", str(code))
    c.expect("bağlı kursun tələbəsinin girişi -> 402", f"{base}/auth/login", 402, method="POST",
             body={"email": s["student_c"], "password": s["password"]})

    print("\n-- parol sınağı (sonuncu: müəllim A-nın açarını bloklayır)")
    for attempt in range(LOGIN_LIMIT):
        _request(f"{base}/auth/login", method="POST",
                 body={"email": s["teacher_a"], "password": f"sehv{attempt}"})
    c.expect(f"{LOGIN_LIMIT} səhvdən sonra DOĞRU şifrə də -> 429", f"{base}/auth/login", 429,
             method="POST", body={"email": s["teacher_a"], "password": s["password"]})
    c.expect("blok başqa istifadəçiyə təsir etmir -> 200", f"{base}/auth/login", 200, method="POST",
             body={"email": s["student_a"], "password": s["password"]})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MasterAI hücum yoxlaması")
    sub = parser.add_subparsers(dest="mode", required=True)
    pub = sub.add_parser("public", help="produksiya: anonim, heç nə yaratmır")
    pub.add_argument("--base", required=True)
    pub.add_argument("--api")
    pub.add_argument("--direct", help="backend-in kənar ünvanı, məs. http://<SERVER_IP>:8110 (AÇILMAMALIDIR)")
    sub.add_parser("seed", help="LOKAL: boş bazaya iki kurs yazır, JSON çap edir")
    full = sub.add_parser("full", help="LOKAL: bütün hücum ssenariləri")
    full.add_argument("--base", required=True)
    full.add_argument("--seed", required=True, help="`seed` çıxışı (JSON)")
    args = parser.parse_args(argv)

    if args.mode == "seed":
        print(json.dumps(_seed()))
        return 0
    c = Checker()
    if args.mode == "public":
        public_checks(c, args.base.rstrip("/"), args.api.rstrip("/") if args.api else None, args.direct)
    else:
        if "127.0.0.1" not in args.base and "localhost" not in args.base:
            raise SystemExit("full rejimi yalnız lokal server üçündür (hesab yaradır, kurs dayandırır)")
        full_checks(c, args.base.rstrip("/"), json.loads(args.seed))
    print(f"\n{c.passed} keçdi, {c.failures} uğursuz")
    print("HAMISI TƏMİZ" if c.failures == 0 else "HÜCUM UĞURLU OLDU - deploy ETMƏ")
    return 0 if c.failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
