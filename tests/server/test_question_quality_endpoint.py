"""`GET /live/question-sets/{id}/quality` — sual keyfiyyəti auditinin
müəllim ekranına açılması.

NİYƏ ENDPOINT: `pipeline/quality.py` audit alətini VPS-də əl ilə skript
kimi işlədirdik. Müəllim isə terminala girə bilmir — 30 sualdan hansını
əvvəl oxumaq lazım olduğunu bilmədən hamısını bərabər gözdən keçirir və
praktikada heç birini oxumur. Audit yalnız müəllimin gördüyü yerdə
dəyər verir.

DİQQƏT: audit cavabın DOĞRU olduğunu demir (bax `pipeline/quality.py`
modul qeydi) — yalnız şübhə əlamətlərini sayır.
"""

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import app, get_question_set_store, get_token_secret, get_user_store
from server.auth import create_token
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"

_CLEAN = MCQQuestion(
    question="Silloqizmdə orta termin neçə dəfə işlənir?",
    options=["Bir dəfə", "İki dəfə", "Üç dəfə", "Dörd dəfə", "Heç"],
    correct_index=1,
    explanation="Orta termin hər iki müqəddimədə iştirak edir, nəticədə isə iştirak etmir.",
)

# Eyni variant iki dəfə → `tekrar_variant` (YÜKSƏK).
_DUPLICATE_OPTION = MCQQuestion(
    question="Hansı fiqurda orta termin subyektdir?",
    options=["Birinci", "Birinci", "İkinci", "Üçüncü", "Dördüncü"],
    correct_index=0,
    explanation="Birinci fiqurda orta termin böyük müqəddimənin subyekti olur.",
)


@pytest.fixture
def env():
    users = UserStore(":memory:")
    question_sets = QuestionSetStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    teacher = users.create("muellim@masternr1.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("telebe@masternr1.az", "hash", "Tələbə")

    qs = question_sets.create(
        subject="mentiq", title="Silloqizmlər", material_kind="link",
        material_location="https://x.az", created_by=teacher["id"],
    )

    yield {
        "client": client, "question_sets": question_sets,
        "teacher": teacher, "student": student, "qs": qs,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _url(env) -> str:
    return f"/live/question-sets/{env['qs']['id']}/quality"


class TestAccess:
    def test_requires_auth(self, env):
        assert env["client"].get(_url(env)).status_code == 401

    def test_non_teacher_gets_403(self, env):
        assert env["client"].get(_url(env), headers=_auth(env["student"])).status_code == 403

    def test_unknown_question_set_returns_404(self, env):
        r = env["client"].get("/live/question-sets/999/quality", headers=_auth(env["teacher"]))
        assert r.status_code == 404


class TestReport:
    def test_empty_set_reports_zero(self, env):
        r = env["client"].get(_url(env), headers=_auth(env["teacher"]))
        assert r.status_code == 200
        assert r.json() == {"question_count": 0, "findings": [], "review_order": []}

    def test_clean_question_has_no_findings(self, env):
        env["question_sets"].add_question(env["qs"]["id"], _CLEAN)
        body = env["client"].get(_url(env), headers=_auth(env["teacher"])).json()
        assert body["question_count"] == 1
        assert body["findings"] == []
        assert body["review_order"] == [1]

    def test_duplicate_option_is_reported_on_its_question_number(self, env):
        env["question_sets"].add_question(env["qs"]["id"], _CLEAN)
        env["question_sets"].add_question(env["qs"]["id"], _DUPLICATE_OPTION)

        body = env["client"].get(_url(env), headers=_auth(env["teacher"])).json()

        assert body["question_count"] == 2
        codes = {(f["code"], f["question_number"]) for f in body["findings"]}
        assert ("tekrar_variant", 2) in codes
        # Şübhəli sual siyahının BAŞINDA olmalıdır — ekranın bütün
        # məqsədi budur.
        assert body["review_order"][0] == 2

    def test_severity_is_sent_as_plain_string(self, env):
        """Client `Severity` enum-unu bilmir; JSON-da `yuksek`/`orta`/
        `asagi` sətri olmalıdır ki, nişan rəngi seçilə bilsin."""
        env["question_sets"].add_question(env["qs"]["id"], _DUPLICATE_OPTION)
        body = env["client"].get(_url(env), headers=_auth(env["teacher"])).json()
        severities = {f["severity"] for f in body["findings"]}
        assert severities <= {"yuksek", "orta", "asagi"}
        assert "yuksek" in severities

    def test_question_numbers_match_the_list_endpoint_order(self, env):
        """Nömrələr `GET .../questions`-un SIRASI ilə eyni olmalıdır —
        əks halda müəllimə səhv sual göstərilər."""
        env["question_sets"].add_question(env["qs"]["id"], _CLEAN)
        env["question_sets"].add_question(env["qs"]["id"], _DUPLICATE_OPTION)

        listed = env["client"].get(
            f"/live/question-sets/{env['qs']['id']}/questions", headers=_auth(env["teacher"])
        ).json()
        body = env["client"].get(_url(env), headers=_auth(env["teacher"])).json()

        suspicious = next(f for f in body["findings"] if f["code"] == "tekrar_variant")
        assert listed[suspicious["question_number"] - 1]["question"] == _DUPLICATE_OPTION.question


class TestMalformedRows:
    """Yazma yolları (add/update) 5 variantı MƏCBUR EDİR, ona görə
    qeyri-standart sətir normal axında yarana bilməz. Amma köhnə/əl ilə
    dəyişdirilmiş data üçün endpoint 500 verməməlidir.

    ƏSAS QƏRAR: belə halda BOŞ hesabat qaytarmaq OLMAZ - ekran «şübhə
    əlaməti tapılmadı» yazar, yəni auditin işlədiyini SANDIRAR. Yalançı
    arxayınlıq auditin heç olmamasından pisdir. Ona görə açıq xəta."""

    def test_row_with_wrong_option_count_returns_409(self, env):
        env["question_sets"].add_question(env["qs"]["id"], _CLEAN)
        # Bazanı birbaşa korla (normal API bunu qəbul etməzdi).
        row = env["question_sets"].list_questions(env["qs"]["id"])[0]
        env["question_sets"]._conn.execute(
            "UPDATE live_questions SET options = ? WHERE id = ?",
            ('["A", "B"]', row["id"]),
        )
        env["question_sets"]._conn.commit()

        r = env["client"].get(_url(env), headers=_auth(env["teacher"]))
        assert r.status_code == 409
        assert "audit" in r.json()["detail"].lower() or "sual" in r.json()["detail"].lower()
