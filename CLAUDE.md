# MasterAI — operativ təlimat

Dövlət qulluğu və magistratura imtahanlarına hazırlaşan tələbələr üçün: dərs
materialını (sayt linki, PDF, şəkil) yükləyir → AI ondan MCQ test sualları
çıxarır → şəxsi/qrup çatında dostlarla birgə canlı "quiz" kimi həll edilir.

**Status: MVP tam uc-uca real production-da təsdiqlənib** (qeydiyyat →
qrup çatı → mesajlaşma (WS) → material yükləmə → AI sual generasiyası →
quiz həlli → xallandırma, real Android emulyatorda, real backend-lə).
`https://masterai.prdostu.com` — real DigitalOcean VPS-də (HTTPS, systemd,
nginx) işləyir. Yeddi backend alt-sistemi tamamlanıb (263 test, `masterai/`
daxilində vahid pytest run — pipeline 57 + backend auth/data 63 + çat
(Faza A+B) 63 + material yükləmə 21 + dostluq 45 + n8n admin 14) + iki
n8n workflow, HƏR İKİSİ aktiv/production-da. Flutter app-ın (`app/`) MVP
nüvəsi yazılıb (22 fayl, bax "Dərs: Flutter app SDK-sız yazıldı") —
istifadəçinin real Windows mühitində `flutter analyze` ("No issues
found!"), `flutter test` (26 test) və `flutter run` (Android Studio AVD,
real cihazda) HƏR ÜÇÜ təsdiqlənib. Uc-uca real test zamanı 2 real backend
bug-ı da tapılıb düzəldilib (bax "Dərs: real material uğursuzluğu" və
"Dərs: Groq `llama-3.3-70b-versatile` modelini dayandırıb").
Brainstorming skill-i ilə alt-sistemlərə bölünür, hər biri öz spec-i ilə
(`docs/superpowers/specs/`).

## Arxitektura

`dildostu/` layihəsinin sınanmış naxışı əsas götürülür (Flutter app + FastAPI
backend, `prdostu.com` alt-domenə DigitalOcean deploy, provider fallback
zənciri). `pipeline/` və `server/` eyni `masterai/` kök venv-ini paylaşır
(bax `requirements.txt`, `.venv/`) — `server/` birbaşa `pipeline/`-i idxal edir.

| Alt-sistem | Nədir | Vəziyyət |
|---|---|---|
| AI sual generasiya pipeline-ı (`pipeline/`) | Material ingestion (sayt/PDF/şəkil) + LangChain LCEL + MCQ çıxarılması | ✅ Tamamlandı (57 test) |
| Backend skeleti: Auth + Data modeli (`server/`) | Email+şifrə auth (bcrypt+JWT), 6 cədvəllik DB sxemi, minimal FastAPI | ✅ Tamamlandı (63 test) |
| Əsas çat: mesajlaşma+WebSocket | `messages` cədvəli, `POST/GET /chats`, `WS /ws/chat/{id}` (real-time mətn, broadcast) | ✅ Tamamlandı (29 test) |
| AI Quiz Orkestrasiyası (Faza B) | Növbəli sual axını (`chat_quiz_sessions`), 45san timeout+erkən keçid, `POST /quiz/start`, WS "answer" tipi, xal | ✅ Tamamlandı (34 test) |
| Dostluq/sosial qraf endpoint-ləri | `POST/GET /friends/requests`, accept/decline/cancel, `GET /friends`, unfriend. `POST /chats` (direct) dostluq şərtinə bağlıdır | ✅ Tamamlandı (45 test) |
| Material yükləmə endpoint-i | `POST/GET /chats/{id}/materials`, `asyncio.to_thread` ilə fon emalı (pipeline→sual+sistem mesajı) | ✅ Tamamlandı (21 test) |
| Flutter app (`app/`) | MVP nüvəsi: qeydiyyat/giriş, çat siyahısı+mesajlaşma (WS), material yükləmə, quiz həlli. Dostluq UI-ı yoxdur (yalnız qrup çatı) | ✅ Tam uc-uca real mühitdə təsdiqlənib (`analyze`+`test`+`run`, real Android emulyator, real backend) — bax `app/README.md` |
| n8n/MCP admin avtomatlaşdırması | Uğursuz material→Telegram bildirişi VƏ gündəlik statistika — HƏR İKİSİ aktiv, n8n.prdostu.com-da | ✅ Tamamlandı (14 test + 2 aktiv real workflow) |
| Deploy | DigitalOcean (`<SERVER_IP>`, dildostu/masternr1 ilə eyni VPS), `https://masterai.prdostu.com`, systemd+nginx+certbot HTTPS | ✅ Tamamlandı — canlı, real `curl`+n8n icrası ilə təsdiqlənib |
| Canlı Sinif Sessiyası (Kahoot-tərzi, Faza 1 — Master NR 1 pilotu üçün) | Müəllim veb host konsolu + tələbə mobil PIN-qoşulma, `docs/superpowers/specs/2026-09-07-masterai-live-classroom-design.md`, `.planning/2026-09-07-masterai-live-classroom/` | ✅ Tam uc-uca REAL test edilib (host+tələbə, real AI sualları, real PIN, sessiya hesabatı) — bax aşağı "Canlı Sinif Sessiyası" bölməsi |
| Ev Təkrarı Rejimi (Faza 2 — asinxron fərdi məşq) | Müəllim tapşırıq təyin edir (veb+mobil, `is_teacher` bayrağı) → tələbə "Tapşırıqlarım"da öz sürəti ilə həll edir → müəllim hesabatda görür, `docs/superpowers/specs/2026-09-07-masterai-homework-mode-design.md`, `.planning/2026-09-07-masterai-homework-mode/` | ✅ Tam uc-uca REAL test edilib (təyin→görmə→həll→hesabat) — bax aşağı "Ev Təkrarı Rejimi" bölməsi |
| Fərdi tələbə tarixçəsi (Faza 3 — canlı sessiya + ev tapşırığı birləşmiş tarixçə) | Tələbə "Mənim tarixçəm"də öz keçmiş nəticələrinə baxır, müəllim istənilən tələbəni seçib eynisini görür, `.planning/2026-09-07-masterai-student-history/` | ✅ Backend+Flutter yazılıb, 404 backend test keçir — istifadəçinin real mühitində HƏLƏ sınanmayıb, bax aşağı "Fərdi tələbə tarixçəsi" bölməsi |

## Canlı Sinif Sessiyası (Faza 1 — Master NR 1 pilotu)

Mövcud tələbə-yönümlü sistemə TOXUNMADAN əlavə olunmuş paralel alt-sistem:
müəllim veb brauzerdə (`flutter run -d chrome`/`build web`) sual bankı
yaradır → AI sualları çıxarır → PIN-li canlı sessiya başladır; tələbələr
hesabsız, yalnız PIN+ad ilə mobil/veb-dən qoşulur, Kahoot-tərzi cavablayır.

**2026-09-07 tarixində TAM UC-UCA REAL TEST edilib** (istifadəçinin real
Windows mühitində, real backend-ə qarşı): sual bankı yaradılması → AI-nın
real 3 sual çıxarması → PIN → tələbənin qoşulması → 3 sualın canlı
göstərilməsi/cavablanması → avtomatik keçid → sessiya bitməsi → host-un
"Sessiya hesabatı" ekranı (yekun sıralama + sual-sual təhlil) — HAMISI
düzgün işlədi. 343 backend test + 32 Flutter test, hamısı keçir.

**Açıq qalan:** real FİZİKİ çoxcihaz (bir neçə AYRI telefon, eyni anda
bir neçə tələbə) miqyas testi — indiyədək yalnız 1 iştirakçı ilə (eyni
noutbukda 2 brauzer sekməsi) sınanıb. Master NR 1 kursuna göstərmək üçün
real sınaq dərsi planlaşdırılmalıdır. Ətraflı tarixçə/qərarlar üçün bax
`.planning/2026-09-07-masterai-live-classroom/progress.md`.

## Ev Təkrarı Rejimi (Faza 2 — asinxron fərdi məşq)

Faza 1-in üzərinə paralel əlavə: müəllim mövcud bir sual bankını
(canlı sessiya üçün yaradılmış) bir qrup çata "ev tapşırığı" kimi son
tarixlə təyin edir (veb host konsolu VƏ mobil çat ekranı — hər ikisi
`is_teacher` bayrağı ilə açılır), tələbə "Tapşırıqlarım" ekranında görüb
öz sürəti ilə həll edir (WebSocket yoxdur, vaxt sayğacı yoxdur, hər
cavabdan sonra dərhal geri bildirim, fasilə/davam mümkün, tək cəhd),
müəllim "Tapşırıq hesabatları" ekranında hər tələbənin statusunu
(gözləyir/davam edir/tamamlanıb+xal) görür.

**2026-09-07 tarixində TAM UC-UCA REAL TEST edilib**: müəllim (veb)
"alma" sual bankından bir çata tapşırıq təyin etdi → tələbə (Android
emulyator, ayrı hesab) "Tapşırıqlarım"da gördü, açıb HƏLL ETDİ →
müəllim hesabatda REAL statusları gördü (özü "gözləyir", tələbə
"tamamlanıb" ✓). 381 backend test + 39 Flutter test, hamısı keçir.
Bu prosesdə real özü-özünə tapılan bir funksional boşluq (hesabata
baxmaq üçün UI unudulmuşdu) aşkarlanıb dərhal düzəldildi.

**Çata qoşulma UI-ı** (real testdə tapılan boşluq, dərhal düzəldildi):
çat siyahısı ekranına "Çata qoşul" ikonu əlavə olundu — çat ID-sini
(mövcud çat sətirlərinin subtitle-ında görünür) əl ilə yazıb özü-özünə
qoşulmaq mümkündür (`POST /chats/{id}/join`, mövcud backend
endpoint-i, dəyişiklik yoxdur).

Növbəti planlaşdırılan fazalar (istifadəçi ilə razılaşdırılıb): Fərdi
tələbə tarixçəsi, Çox-müəllimli idarəetmə, Sual redaktə/təsdiq ekranı.
Ətraflı tarixçə/qərarlar üçün bax
`.planning/2026-09-07-masterai-homework-mode/progress.md`.

## Fərdi tələbə tarixçəsi (Faza 3)

Faza 1+2-nin üzərinə: tələbənin canlı sessiya VƏ ev tapşırığı
nəticələri eyni xronoloji siyahıda birləşdirilir. Tələbə "Mənim
tarixçəm" ekranında öz nəticələrinə baxır, müəllim "Fərdi tələbə
tarixçəsi" ekranından (çat seç → üzv seç) istənilən tələbənin
tarixçəsinə baxır (yalnız ortaq çatı olan tələbələr üçün icazə verilir).

**Real arxitektura boşluğu tapılıb düzəldilib:** `live_participants`
əvvəllər `users`-a bağlı deyildi (PIN qoşulması qəsdən hesabsızdır).
İndi `WS /ws/live/{pin}/play` join mesajına KÖNÜLLÜ `token` sahəsi
əlavə olundu — yalnız daxil olmuş istifadəçi qoşulanda dolur (bax
"join-after-login" bölməsi, `chat_list_screen.dart`-dakı "Sinif
sessiyasına qoşul" ikonu), etibarsız/köhnə token qoşulmanı RƏDD ETMİR,
sadəcə anonim kimi davam edir — pre-login PIN axını dəyişməz qalır.

**Vəziyyət (2026-09-07):** Backend 404 test keçir (əvvəlki 381 + 23
yeni). Flutter tərəfi (`ui/history/`) yazılıb, istifadəçinin real
mühitində (`flutter analyze`+`test`+`run`, canlı sessiya+ev tapşırığı
uc-uca) HƏLƏ sınanmayıb. Ətraflı bax
`.planning/2026-09-07-masterai-student-history/progress.md`.

## Giriş formatları (pipeline)

Sistemimiz üç növ materialı dəstəkləyir:
- **Sayt linki** — BeautifulSoup/Selenium scraping
- **PDF** — pypdf ilə mətn çıxarılması
- **Şəkil** — pytesseract OCR

## Bilinən risklər (production-dan əvvəl həll edilməli)

- **WebSocket JWT query param-da (`?token=...`)** — brauzer WebSocket
  API-si custom header dəstəkləmədiyi üçün belə edilib, amma real smoke
  testində uvicorn access log-unda tam token açıq mətn kimi göründüyü
  təsdiqləndi. Deploy-dan əvvəl: ya log-larda maskalama, ya da qısaömürlü
  WS-özəl "ticket" tokeni ilə əvəzlə (bax
  `docs/superpowers/specs/2026-09-02-chat-messaging-design.md`, bölmə 4).
- ~~`_notify_admin_webhook()` real production-da hələ sınanmayıb~~ —
  **✅ TƏSDİQLƏNDİ (2026-09-03):** Flutter app-ın real mühit testində
  (qrup çatına sayt linki yükləndi, emal uğursuz oldu — bax aşağıdakı
  "Dərs: real material uğursuzluğu" bölməsi) backend real şəkildə
  `_notify_admin_webhook()`-u çağırdı və Telegram-a bildiriş REAL
  gəldi (istifadəçi təsdiqlədi). Uc-uca zəncir (backend material
  emalı → n8n webhook → Telegram) indi tam real şəraitdə yoxlanılıb.

## Dərs: bütün Store sinifləri `threading.Lock`/`RLock` işlədir

`sqlite3.connect(path, check_same_thread=False)` YALNIZ Python-un thread-
yoxlamasını söndürür, bağlantını thread-safe ETMİR (bax
`server/user_store.py` və digər Store-ların modul qeydi). Bu, real
WebSocket inteqrasiya testində (2 istifadəçi eyni anda cavablayır) sqlite
korlanmasına (`OperationalError: cannot commit`) səbəb oldu — real
tək-prosesli `uvicorn` deploy-unda bu problem YOXDUR (təsdiqlənib, bax
`.planning/2026-09-02-masterai-quiz-orchestration/`), amma çoxlu-thread
test mühitlərində (Starlette `TestClient`-in hər WebSocket bağlantısını
ayrı OS thread-ində işlətməsi) və gələcək `--workers`/çoxlu-thread
ssenarilərində qorunmaq üçün **hər yeni Store sinfi də daxili kilid
işlətməlidir** (nested public-metod çağırışı varsa `RLock`, yoxdursa
sadə `Lock`).

## Dərs: real deploy zamanı rast gəlinən tələlər (VPS-ə aid, kod problemi deyil)

1. **VPS-dəki `/opt/pr-agent/repo` checkout-u `main` branch-indədir** —
   bizim işimiz `claude/ai-engineering-monthly-project-g5cg2y`-dadır.
   `git pull` sükutla `main`-i yeniləyir, `masterai/` görünmür. Deploy-dan
   əvvəl HƏMİŞƏ `git checkout claude/ai-engineering-monthly-project-g5cg2y`
   (və ya işlənən branch) yoxla.
2. **`ufw` yalnız `22`+`443` icazə verirdi, `80` YOX idi** — certbot-un
   HTTP-01 doğrulaması (`/.well-known/acme-challenge/...`) port 80
   tələb edir, "Timeout during connect (likely firewall problem)" xətası
   verdi. Həlli: `ufw allow 80/tcp`. Digər `prdostu.com` alt-domenləri
   üçün də bu VPS-də eyni yoxlama edilməlidir.
3. **n8n MCP-nin credential yaratma aləti YOXDUR** (təhlükəsizlik
   səbəbindən) — `httpHeaderAuth` kimi kredensiallar yalnız n8n UI-dan
   əl ilə yaradıla bilər, sonra `update_workflow`-un `setNodeCredential`
   əməliyyatı ilə node-a bağlanır. UI-da "Name" sahəsi HEADER ADI-dır
   (məs. `X-Admin-Key`), kredensialın öz adı ayrı sahədir (başlıq) —
   qarışdırılması asandır.
4. **Bu VPS-in DigitalOcean abunəliyi bitib deaktiv olsa, DÖRD şey eyni
   anda düşür** — masterai, dildostu-live, masternr1 (aktiv pilot!) və
   n8n, hamısı `<SERVER_IP>`-u paylaşır. Real hadisə: abunəlik bitdi,
   VPS tam əlçatmaz oldu (SSH/HTTPS/ping — HAMISI timeout), Flutter
   app-da real telefonda "Bağlantı xətası" bununla izah olundu (kod
   bug-ı DEYİL). Bu VPS-in abunəlik/ödəniş statusu digər layihələrdən
   asılı olmayaraq mütəmadi yoxlanılmalıdır — bir hesabın bitməsi üç
   layihəni birdən öldürür.
5. **`tesseract-ocr` VPS-də quraşdırılmayıb** — real telefonda şəkil
   materialı yükləndikdə "Material emalı uğursuz oldu: tesseract is
   not installed or it's not in your PATH" xətası verdi (`pytesseract`
   sistemdə `tesseract` binarını axtarır, Python paketi kifayət etmir).
   Həlli: `apt install -y tesseract-ocr` (servisi restart etmək lazım
   deyil, hər çağırışda binar yenidən axtarılır). `requirements.txt`-də
   bu sistem asılılığı qeyd olunmayıb — gələcək VPS-lərdə deploy
   skriptinə (`deploy_on_droplet.sh`) əlavə edilməlidir.

## Dərs: real material uğursuzluğu — Wikipedia `requests`-in defolt User-Agent-ini bloklayır

Flutter app-ın real emulyator (Android Studio AVD) testində qrup çatına
sayt linki (`az.wikipedia.org`) yükləndi, backend "Sayt yüklənmədi" ilə
uğursuz oldu. VPS-də birbaşa reproduksiya edildi:
`requests.get(url)` (heç bir header-siz) → **403**, eyni sorğu brauzer
`User-Agent`-i ilə → **200**. Kök səbəb: Wikimedia `python-requests/...`
kimi bot-görünüşlü UA-ları rədd edir. `pipeline/ingestion/web_extractor.py`-da
`_download_static()`-a sabit brauzer `User-Agent` header-i əlavə olundu
(test: `test_download_static_sends_browser_user_agent`, 264 test).
**Bu, "mənbədən yoxla" prinsipinin daha bir nümunəsidir** — pytest-in
mock-lanmış fixture-ları bunu görə bilməzdi, yalnız real bir saytla real
şəbəkə sorğusu tapdı. Eyni zamanda bu hadisə "Bilinən risklər"dəki
`_notify_admin_webhook()` sınağını da real təsdiqlədi (Telegram-a real
bildiriş gəldi).

## Dərs: Groq `llama-3.3-70b-versatile` modelini dayandırıb

Wikipedia fetch düzəlişindən (yuxarı bax) sonra material emalı yenə uğursuz
oldu, amma fərqli xəta ilə: "Kifayət qədər keyfiyyətli sual alınmadı
(0 < 3)". VPS-də birbaşa reproduksiya: `complete_with_fallback()` çağırışı
Groq-dan **404 model_not_found** aldı (`llama-3.3-70b-versatile` artıq
mövcud deyil), Ollama fallback-ı da VPS-də quraşdırılmadığı üçün (gözlənilən
— yalnız lokal) uğursuz oldu, `claude` provider-i isə heç konfiqurasiya
olunmayıb (`ANTHROPIC_API_KEY` yoxdur) — nəticədə bütün provider-lər
uğursuz oldu. `client.models.list()` ilə hesabın canlı model siyahısı
sorğulandı (sənəd yox, HƏQİQİ API cavabı) — `llama-3.3-70b-versatile`
siyahıda YOXDUR, Groq artıq əsasən `openai/gpt-oss-*`, `qwen/*` modellərini
saxlayır. `pipeline/providers.py`-də defolt `GROQ_MODEL`
`openai/gpt-oss-120b`-yə dəyişdirildi (`.env.example` də yeniləndi).
**Diqqət: `dildostu/server/dildostu_server/providers.py`-də də eyni
köhnəlmiş defolt var** (bu tapşırığın əhatəsindən kənar saxlanıldı, ayrıca
düzəldilməlidir). Bu, "mənbədən yoxla" prinsipinin daha bir nümunəsidir —
LLM provider-lərin model kataloqu vaxtaşırı dəyişir, kodda sabit yazılmış
model adı sükutla köhnəlib sınmaya bilər; pytest mock-ları bunu görə
bilməz, yalnız real API çağırışı aşkar edir.

## Dərs: Flutter app SDK-sız yazıldı, sonra istifadəçinin real mühitində sınandı

`app/` bu sandbox-da (Flutter SDK YOXDUR) yazılıb, sonra istifadəçinin
Windows mühitində (`flutter pub get`/`analyze`/`test`) REAL yoxlanıldı.
Özünü-nəzərdən keçirmədə (SDK-sız) 2 bug, real icrada isə 3 ƏLAVƏ bug
tapılıb düzəldilib — cəmi 5:

**SDK-sız özünü-nəzərdən keçirmədə tapılan (2):**
1. Dart string interpolasiyası: `'($resp.statusCode)'` `resp`-i
   `toString()`-lə çap edib sonra hərfi ".statusCode)" yazardı —
   property access `${}` tələb edir, bare `$` yalnız sadə
   identifikatorlar üçündür.
2. Quiz sual kartının "bağlıdır" statusu yalnız lokal tap-i izləyirdi —
   çat yenidən açılanda artıq nəticəsi gəlmiş (`QuizResultItem`) sual
   kartı hələ aktiv görünüb toxunanda backend-in `AlreadyAnswered`
   xətası alınırdı.

**İstifadəçinin real mühitində (`flutter pub get`/`analyze`/`test`) tapılan (3):**
3. **`flutter pub get`:** `flutter_secure_storage ^11` (`win32 ^6.0.1`)
   və `file_picker ^10.1.2` (`win32 ^5.9.0`) versiya toqquşması —
   `file_picker: ^12.2.0`-a yüksəldildi.
4. **`flutter analyze`:** `file_picker` 10→12 yüksəldilməsi API-ni
   dəyişmişdi — `FilePicker.platform` artıq YOXDUR, statik metodlar
   birbaşa `FilePicker`-dədir (`FilePicker.pickFile(...)`).
5. **`flutter test`:** iki ayrı problem —
   a) `Building native assets for package:objective_c failed` (boşluqlu
      Windows yolu hook script-ini qırır) — `dildostu/app/pubspec.yaml`-da
      ARTIQ HƏLL EDİLMİŞ eyni problem, eyni `dependency_overrides`
      (`path_provider_android: 2.2.23`, `path_provider_foundation: 2.4.4`)
      tətbiq edildi;
   b) `http.Response(String, int)` konstruktorunun `encoding` adlı
      parametri YOXDUR (mənim ilk düzəlişim — `encoding: utf8` — buna görə
      compile xətası verdi, istifadəçinin real paket mənbəyini
      göstərməsi ilə üzə çıxdı). Kodlaşdırma daxili olaraq `headers`-dəki
      `content-type`-dan törədilir: `application/json` olsa avtomatik
      utf8, əks halda (header göndərilməsə də) defolt **latin1** —
      Azərbaycan hərfli test fikstürləri (`'Əli'`) sükutla xəta atırdı,
      bu da client kodunun geniş `catch (_)`-i tərəfindən "şəbəkə xətası"
      kimi gizlənirdi. Doğru həlli: `http.Response(body, code, headers:
      {'content-type': 'application/json'})`.

**Vəziyyət:** `flutter analyze` — "No issues found!" (təsdiqlənib).
`flutter test` — **26 test, hamısı keçdi** (təsdiqlənib, düzəliş 5b-dən
sonra). İlk addım (yeni Flutter işi başlayanda) həmişə: `cd app &&
flutter pub get && flutter analyze && flutter test` (bax
`app/README.md`) — bu 5 bug SDK olmadan tapıla BİLMƏZDİ, "mənbədən
yoxla" prinsipinin canlı nümunəsidir (ilk səhv düzəliş də daxil
olmaqla — mən özüm yoxlamadan güman etdim, istifadəçinin real paket
mənbəyini göstərməsi ilə düzəldi).

## Dərs: veb host konsolunda CORS unudulmuşdu — backend HEÇ VAXT brauzerdən çağırılmamışdı

Faza 4-ün (Canlı Sinif Sessiyası, host konsolu) real brauzer testində
(`flutter run -d chrome`, istifadəçinin real Windows mühitində) giriş
formasında "Bağlantı xətası" alındı, baxmayaraq ki eyni backend mobil
tərəfdən (`flutter run` Android emulyator/cihaz) aylardır problemsiz
işləyir. Kök səbəb: `server/app.py`-də HEÇ VAXT `CORSMiddleware`
qurulmayıb — mobil HTTP client-i brauzerin same-origin siyasətinə tabe
deyil, ona görə bu problem indiyə qədər ÜZƏ ÇIXMAMIŞDI (bütün əvvəlki 341
test və real mobil test bunu görə bilməzdi). `localhost:...`-dan
`https://masterai.prdostu.com`-a `fetch`/`XMLHttpRequest` (Flutter
`http` paketinin veb tərəfi bunları işlədir) cross-origin sayılır,
server `Access-Control-Allow-Origin` header-i qaytarmadığı üçün brauzer
cavabı client koduna çatdırmır — bu da bizim `ApiException`-ın geniş
`catch (_)`-i tərəfindən "şəbəkə xətası" kimi göstərilir (eyni
gizlətmə naxışı `dildostu` UA-403 dərsində də olub).

Həll: `app.add_middleware(CORSMiddleware, allow_origins=["*"],
allow_credentials=False, allow_methods=["*"], allow_headers=["*"])`
əlavə edildi (`allow_credentials=False` MƏCBURİDİR —
`allow_origins=["*"]` ilə `True` uyğun gəlmir, üstəlik auth Bearer
header-lə aparılır, cookie/credential yoxdur, ona görə wildcard
təhlükəsizdir). Testlər: `TestCors` (`tests/server/test_app.py`) —
adi sorğuda `access-control-allow-origin: *` VƏ preflight (`OPTIONS` +
`Access-Control-Request-Method`) sorğusunun 200 qaytardığını yoxlayır
(343/343 test keçir). **Bu, "mənbədən yoxla" prinsipinin daha bir
nümunəsidir** — CORS SƏLƏHLƏNMƏSİ yalnız real brauzerdə, real
cross-origin sorğu ilə üzə çıxır, pytest-in `TestClient`-i (server
prosesinin daxilindən çağırdığı üçün) və mobil `flutter run` bunu
GÖRƏ BİLMƏZ. **Diqqət:** bu düzəliş hələ VPS-ə deploy EDİLMƏYİB
(`git pull` + `systemctl restart masterai` lazımdır) — deploy-dan sonra
Chrome-da yenidən sınanmalıdır.

## Qeyd

Ad seçimi ilə bağlı: repoda `masternr1/` (Master NR 1 tədris mərkəzi üçün AI
müştəri köməkçisi) mövcuddur — fərqli məhsuldur, adların oxşarlığına diqqət et.
