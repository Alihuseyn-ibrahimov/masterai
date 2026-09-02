# MasterAI — Backend Skeleti: Auth + Data Modeli (Dizayn Sənədi)

**Tarix:** 2026-09-02
**Status:** Təsdiqlənib (istifadəçi tərəfindən), implementasiya planına keçilir
**Əhatə dairəsi:** Yalnız bu alt-sistem — istifadəçi qeydiyyatı/girişi (auth)
və bütün əsas varlıqların (users/friendships/chats/materials/questions/
quiz_attempts) DB sxemi + minimal FastAPI skeleti. Dostluq/çat/material
CRUD endpoint-ləri, WebSocket çat, Flutter tətbiqi bu sənədin əhatəsindən
**kənardadır** — ayrı spec-lər olaraq gələcəkdə dizayn ediləcək.

## 1. Problem və məqsəd

MasterAI-ın bütün digər alt-sistemləri (çat, sosial qraf, quiz axını) bir
istifadəçi identifikasiyası və vahid data modelinə ehtiyac duyur. Bu sənəd
yalnız o təməli təsvir edir: `masterai/server/masterai_server/` FastAPI
paketi — auth + DB sxemi.

**Niyə indi:** AI sual generasiya pipeline-ı (əvvəlki spec, tamamlanıb)
artıq `MCQQuestion` massivi istehsal edir — bu massivin haradasa
saxlanması lazımdır ki, gələcək alt-sistemlər (çat, quiz UI) onun
üzərində qura bilsin.

## 2. Arxitektura

`dildostu/server`-in Store/auth kod naxışı təkrarlanır, amma **layihə
strukturu fərqlidir**: dildostu-da `app/` (Flutter) və `server/` (Python)
tamam ayrı toolchain-lərdir, ona görə ayrı venv-ləri var. MasterAI-da isə
`server/` birbaşa `pipeline/`-i idxal edir (hər ikisi Python) — ona görə
**tək paylaşılan venv/pyproject** (artıq mövcud `masterai/pyproject.toml`
və `masterai/.venv`) işlədilir, `server/` onun bir alt-paketi olur:

```
masterai/
  pyproject.toml       # mövcud, dəyişməz (pythonpath = ["."])
  requirements.txt        # mövcud, server asılılıqları (fastapi, bcrypt, s.) əlavə olunur
  .venv/                     # mövcud, paylaşılan
  pipeline/                     # (tamamlanıb, əvvəlki spec)
  server/
    __init__.py
    auth.py             # bcrypt hash + JWT — dildostu/server/auth.py-dan demək olar eyni köçürülür
    user_store.py         # UserStore — sqlite3, dildostu/server/user_store.py naxışı
    friendship_store.py     # FriendshipStore
    chat_store.py             # ChatStore + ChatMemberStore
    material_store.py           # MaterialStore
    question_store.py             # QuestionStore
    quiz_attempt_store.py           # QuizAttemptStore
    app.py                            # FastAPI: /auth/register, /auth/login, /health
  tests/
    server/
      __init__.py
      test_auth.py
      test_user_store.py
      test_friendship_store.py
      test_chat_store.py
      test_material_store.py
      test_question_store.py
      test_quiz_attempt_store.py
      test_app.py
```

Test importları: `from server.auth import ...` (`server/__init__.py` onu
`masterai` kök pythonpath-ından adi alt-paket edir).

**Store deseni:** hər Store sinfi öz cədvəlinin sxemini `_init_schema()`-da
yaradır (`CREATE TABLE IF NOT EXISTS`), `sqlite3.connect(path,
check_same_thread=False)`, `row_factory = sqlite3.Row`. ORM işlədilmir —
`dildostu/server`-də sınanmış, tələbənin artıq bildiyi yanaşma.

**Store-ların dərinliyi bu fazada:** yalnız `UserStore` tam funksionaldır
(auth ona bağlıdır). `FriendshipStore`/`ChatStore`/`MaterialStore`/
`QuestionStore`/`QuizAttemptStore` bu fazada **yalnız sxem + minimal
`create`/`get`/`list_by_user`** metodları alır — sxemin özünün doğru
olduğunu test etmək üçün kifayətdir. Domen məntiqi (dostluq qəbul/rədd
axını, çat mesajlaşması, material yükləmə axını) həmin funksionallığın
öz endpoint spec-i dizayn ediləndə həmin Store-a əlavə olunur, indi
yazılmır (bax bölmə 7 — bunlar əhatə xaricindədir).

**Pipeline asılılığı:** `server/` `pipeline/`-i birbaşa idxal edir
(`from pipeline.pipeline import generate_quiz`) — hər ikisi eyni
`masterai/` kökündə, eyni pythonpath-dadır, ayrıca paketləmə/pip install
tələb olunmur.

## 3. DB sxemi

Bütün cədvəllər `sqlite3`, `created_at`/`answered_at` UTC ISO mətn kimi.

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    phone         TEXT UNIQUE,          -- NULL-a bilər, gələcək OTP üçün yer
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE friendships (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_id  INTEGER NOT NULL REFERENCES users(id),
    addressee_id  INTEGER NOT NULL REFERENCES users(id),
    status        TEXT NOT NULL,        -- 'pending' | 'accepted' | 'declined'
    created_at    TEXT NOT NULL,
    responded_at  TEXT,
    UNIQUE(requester_id, addressee_id)
);

CREATE TABLE chats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,          -- 'direct' | 'group'
    name        TEXT,                   -- 'direct' üçün NULL
    created_by  INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL
);

CREATE TABLE chat_members (
    chat_id   INTEGER NOT NULL REFERENCES chats(id),
    user_id   INTEGER NOT NULL REFERENCES users(id),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE materials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL REFERENCES chats(id),
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    kind        TEXT NOT NULL,          -- 'link' | 'pdf' | 'image'
    location    TEXT NOT NULL,
    status      TEXT NOT NULL,          -- 'processing' | 'ready' | 'failed'
    created_at  TEXT NOT NULL
);

CREATE TABLE questions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id    INTEGER NOT NULL REFERENCES materials(id),
    question       TEXT NOT NULL,
    options        TEXT NOT NULL,       -- JSON massiv, tam 5 element
    correct_index  INTEGER NOT NULL,
    explanation    TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE TABLE quiz_attempts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id  INTEGER NOT NULL REFERENCES questions(id),
    user_id      INTEGER NOT NULL REFERENCES users(id),
    chosen_index INTEGER NOT NULL,
    is_correct   INTEGER NOT NULL,      -- 0 | 1
    answered_at  TEXT NOT NULL
);
```

`questions` cədvəli pipeline-ın `MCQQuestion` Pydantic modelini birbaşa
əks etdirir (`options` JSON-a serialize olunur) — QuestionStore bu iki
format arasında çevrilməni öz üzərinə götürür.

## 4. Auth axını

`dildostu/server/auth.py` demək olar dəyişmədən köçürülür:

- `hash_password(password) -> str` — bcrypt, öz duzu ilə
- `verify_password(password, password_hash) -> bool` — xarab hash halında
  `False` (istisna atmır)
- `create_token(user_id, *, secret, expires_in_seconds) -> str` — JWT HS256
- `verify_token(token, *, secret) -> int` — `user_id` qaytarır, etibarsızdırsa
  `InvalidToken`
- `token_secret() -> str` — `JWT_SECRET` env-dən (≥32 simvol, yoxdursa
  `RuntimeError` — sabit/boş defolt açar YOXDUR)

**Endpoint-lər:**
- `POST /auth/register` — `{email, password, display_name}` →
  `{user_id, token}`. E-poçt artıq mövcuddursa `409`.
- `POST /auth/login` — `{email, password}` → `{user_id, token}`. Yanlış
  kombinasiyada `401` (email tapılmadı/şifrə səhvdir — eyni mesaj, user
  enumeration-un qarşısını almaq üçün).
- `GET /health` — `{"status": "ok"}`, DB bağlantısının işlək olduğunu
  yoxlayır (sadə `SELECT 1`).

Token TTL: 90 gün (dildostu-dakı `DEFAULT_TOKEN_TTL_SECONDS` ilə eyni —
mobil app üçün uzun ömür, istifadəçi tez-tez giriş etməsin).

## 5. Xəta idarəetməsi

- **Dublikat e-poçt qeydiyyatı** → `DuplicateEmail` (Store səviyyəsində) →
  endpoint-də `409 Conflict`
- **Yanlış giriş** → `401 Unauthorized`, generik mesaj (enumeration qarşısı)
- **`JWT_SECRET` təyin olunmayıb** → server başlanğıcında `RuntimeError`
  (səssiz defolt açarla işə düşmür — təhlükəsizlik qaydası)
- **Etibarsız/vaxtı keçmiş token** → `InvalidToken` → qorunan endpoint-lərdə
  `401`
- Store metodları DB xətasında (məs. FK pozulması) sqlite3-ün öz
  istisnasını (`sqlite3.IntegrityError`) atır — endpoint qatı bunu `400`-ə
  çevirir, səssiz udmur

## 6. Test strategiyası

- Hər Store sinfi üçün TDD, müvəqqəti sqlite faylı (`tmp_path` fixture)
  ilə: yaratma, oxuma, unikal məhdudiyyət pozulması, FK referansları
- `test_auth.py` — dildostu-nun `test_auth.py`-i əsas götürülür: hash/verify
  simmetriyası, token yaratma/doğrulama, vaxtı keçmiş/saxta token rəddi
- `test_app.py` — `httpx.TestClient` ilə `/auth/register`→`/auth/login`→
  qorunan endpoint axını, dublikat qeydiyyat, yanlış şifrə ssenariləri
- Pipeline inteqrasiyası bu fazada test edilmir (QuestionStore-un
  `MCQQuestion`↔DB çevrilməsi test olunur, amma `generate_quiz()`-in özü
  ayrı, artıq tamamlanmış spec-in məsuliyyətindədir)

## 7. Əhatə xaricində (gələcək spec-lər)

- Dostluq sorğusu göndərmə/qəbul endpoint-ləri (`POST /friendships`, s.)
- Çat yaratma/mesajlaşma, WebSocket
- Material yükləmə endpoint-i (pipeline-ı tetikləyən) — bu, `materials`
  cədvəlini artıq işlədəcək, amma HTTP səthi ayrı spec-dir
- Flutter app skeleti (bu sandbox-da Flutter SDK yoxdur, istifadəçinin öz
  mühitində ayrıca dizayn ediləcək)
- Telefon/OTP auth (DB-də `phone` sütunu üçün yer saxlanılıb, məntiq yoxdur)
