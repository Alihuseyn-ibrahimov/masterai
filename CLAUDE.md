# MasterAI — operativ təlimat

Dövlət qulluğu və magistratura imtahanlarına hazırlaşan tələbələr üçün: dərs
materialını (sayt linki, PDF, şəkil) yükləyir → AI ondan MCQ test sualları
çıxarır → şəxsi/qrup çatında dostlarla birgə canlı "quiz" kimi həll edilir.

**Status: aktiv inkişafda.** Yeddi alt-sistem tamamlanıb (263 test,
`masterai/` daxilində vahid pytest run — pipeline 57 + backend auth/data
63 + çat (Faza A+B) 63 + material yükləmə 21 + dostluq 45 + n8n admin
14) + iki real n8n workflow (bax aşağı). Deploy sənədləşdirilib
(`DEPLOY.md` + `deploy/`), icra gözləyir — bax aşağı, "Deploy" sətri.
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
| Flutter app | Bu sandbox-da Flutter SDK yoxdur — istifadəçinin öz mühitində | Planlaşdırılıb |
| n8n/MCP admin avtomatlaşdırması | Uğursuz material→Telegram bildirişi (aktiv), gündəlik statistika (deploy-u gözləyir) — n8n.prdostu.com-da | ✅ Tamamlandı (14 test + 2 real workflow) |
| Deploy | DigitalOcean (`<SERVER_IP>`, dildostu/masternr1 ilə eyni VPS), `masterai.prdostu.com`, systemd+nginx+certbot — `DEPLOY.md` + `deploy/deploy_on_droplet.sh` hazır | Sənədləşdirilib, icra gözləyir (bu sandbox-da SSH/scp yoxdur) |

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
- **n8n "Gündəlik Statistika" workflow-u deploy-u gözləyir** —
  `Ghlqz9ZHM3RXiRjS` (n8n.prdostu.com) BİLƏRƏKDƏN aktivləşdirilməyib:
  `Statistikanı Çək` (HTTP Request) node-unun URL-i placeholder,
  "MasterAI Admin Key" kredensialının dəyəri yoxdur. Deploy-dan sonra:
  URL-i real domenə (`https://masterai.prdostu.com/admin/stats`) yenilə,
  admin key kredensialına real `ADMIN_API_KEY` dəyərini yaz, sonra
  `publish_workflow` (addım-addım bax `DEPLOY.md` bölmə 6).
- **Deploy sənədləşdirilib, icra edilməyib** — `DEPLOY.md` + `deploy/`
  qovluğu (systemd/nginx/skript) dildostu/masternr1 naxışına uyğun
  yazılıb, amma bu sandbox-da `ssh`/`scp` YOXDUR — real icra
  istifadəçinin öz mühitindən və ya SSH-a malik gələcək sessiyadan
  edilməlidir. Bu, "Deploy" ✅ tamamlanıb demək DEYİL — yalnız hazırlıq.
- **Sandbox↔n8n şəbəkə əlaqəsi bu mühitdə bloklanıb** — bu sandbox-un
  egress siyasəti `n8n.prdostu.com`-a çıxışı bloklayır (test zamanı
  aşkarlandı). Real deploy serverində adi internet çıxışı olacağı üçün
  `_notify_admin_webhook()` normal işləməlidir — amma deploy-dan sonra
  bunu real bir uğursuz material yükləməsi ilə YENİDƏN yoxlamaq lazımdır
  (bu sandbox-da doğrulanmayıb, yalnız n8n-in özündə `test_workflow`
  ilə təcrid olunmuş halda doğrulanıb).

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

## Qeyd

Ad seçimi ilə bağlı: repoda `masternr1/` (Master NR 1 tədris mərkəzi üçün AI
müştəri köməkçisi) mövcuddur — fərqli məhsuldur, adların oxşarlığına diqqət et.
