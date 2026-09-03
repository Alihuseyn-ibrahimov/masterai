# MasterAI — operativ təlimat

Dövlət qulluğu və magistratura imtahanlarına hazırlaşan tələbələr üçün: dərs
materialını (sayt linki, PDF, şəkil) yükləyir → AI ondan MCQ test sualları
çıxarır → şəxsi/qrup çatında dostlarla birgə canlı "quiz" kimi həll edilir.

**Status: backend canlıdır, Flutter app kod tərəfi yazılıb (yoxlanmayıb).**
`https://masterai.prdostu.com` — real DigitalOcean VPS-də (HTTPS, systemd,
nginx) işləyir. Yeddi backend alt-sistemi tamamlanıb (263 test, `masterai/`
daxilində vahid pytest run — pipeline 57 + backend auth/data 63 + çat
(Faza A+B) 63 + material yükləmə 21 + dostluq 45 + n8n admin 14) + iki
n8n workflow, HƏR İKİSİ aktiv/production-da. Flutter app-ın (`app/`) MVP
nüvəsi yazılıb (22 fayl, bax "Dərs: Flutter app SDK-sız yazıldı"), real
yoxlama istifadəçinin öz mühitindədir. Brainstorming skill-i ilə
alt-sistemlərə bölünür, hər biri öz spec-i ilə (`docs/superpowers/specs/`).

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
| Flutter app (`app/`) | MVP nüvəsi: qeydiyyat/giriş, çat siyahısı+mesajlaşma (WS), material yükləmə, quiz həlli. Dostluq UI-ı yoxdur (yalnız qrup çatı) | Kod yazılıb (22 fayl), `flutter analyze`/`test`/`run` istifadəçinin öz mühitini gözləyir — bax `app/README.md` |
| n8n/MCP admin avtomatlaşdırması | Uğursuz material→Telegram bildirişi VƏ gündəlik statistika — HƏR İKİSİ aktiv, n8n.prdostu.com-da | ✅ Tamamlandı (14 test + 2 aktiv real workflow) |
| Deploy | DigitalOcean (`<SERVER_IP>`, dildostu/masternr1 ilə eyni VPS), `https://masterai.prdostu.com`, systemd+nginx+certbot HTTPS | ✅ Tamamlandı — canlı, real `curl`+n8n icrası ilə təsdiqlənib |

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
- **`_notify_admin_webhook()` real production-da hələ sınanmayıb** —
  n8n-in "Uğursuz Material Bildirişi" workflow-u aktivdir və Telegram
  çatdırılması ayrıca (n8n-in öz `test_workflow`-u ilə) təsdiqlənib, amma
  backend-in ÖZÜNÜN real material uğursuzluğu zamanı bu webhook-u
  çağırdığı hələ real production-da izlənməyib (yalnız pytest-də mock
  ilə). İlk real uğursuz material yükləməsində Telegram-a bildiriş
  gəldiyini yoxla.

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

## Dərs: real deploy zamanı rast gəlinən 3 tələ (VPS-ə aid, kod problemi deyil)

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

**Vəziyyət:** `flutter analyze` real mühitdə "No issues found!" verdi
(təsdiqlənib). `flutter test`-in düzəliş (5b) tətbiq olunub, real
təsdiq (istifadəçinin `flutter test` təkrar icrası) növbəti addımdır.
İlk addım (yeni Flutter işi başlayanda) həmişə: `cd app && flutter pub
get && flutter analyze && flutter test` (bax `app/README.md`) — bu 5
bug SDK olmadan tapıla BİLMƏZDİ, "mənbədən yoxla" prinsipinin canlı
nümunəsidir (ilk səhv düzəliş də daxil olmaqla — mən özüm yoxlamadan
güman etdim, istifadəçinin real paket mənbəyini göstərməsi ilə düzəldi).

## Qeyd

Ad seçimi ilə bağlı: repoda `masternr1/` (Master NR 1 tədris mərkəzi üçün AI
müştəri köməkçisi) mövcuddur — fərqli məhsuldur, adların oxşarlığına diqqət et.
