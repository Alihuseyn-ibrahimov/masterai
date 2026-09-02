# MasterAI — operativ təlimat

Dövlət qulluğu və magistratura imtahanlarına hazırlaşan tələbələr üçün: dərs
materialını (sayt linki, PDF, şəkil) yükləyir → AI ondan MCQ test sualları
çıxarır → şəxsi/qrup çatında dostlarla birgə canlı "quiz" kimi həll edilir.

**Status: aktiv inkişafda.** İki alt-sistem TDD ilə tamamlanıb (120+57=177
test — bax hər alt-sistemin öz `.planning/` qovluğu üçün faktiki say).
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
| Çat infrastrukturu | Şəxsi+qrup çatlar, WebSocket, AI bot iştirakçı | Planlaşdırılıb |
| Dostluq/sosial qraf endpoint-ləri | Sorğu göndər/qəbul/rədd HTTP-si (DB sxemi hazırdır) | Planlaşdırılıb |
| Material yükləmə endpoint-i | Pipeline-ı tetikləyən HTTP səthi | Planlaşdırılıb |
| Flutter app | Bu sandbox-da Flutter SDK yoxdur — istifadəçinin öz mühitində | Planlaşdırılıb |
| n8n/MCP orkestrasiya | Material yükləndikdə tetiklənən pipeline, admin alətləri | Planlaşdırılıb |
| Deploy | DigitalOcean, systemd, Cloudflare | Planlaşdırılıb |

## Giriş formatları (pipeline)

Sistemimiz üç növ materialı dəstəkləyir:
- **Sayt linki** — BeautifulSoup/Selenium scraping
- **PDF** — pypdf ilə mətn çıxarılması
- **Şəkil** — pytesseract OCR

## Qeyd

Ad seçimi ilə bağlı: repoda `masternr1/` (Master NR 1 tədris mərkəzi üçün AI
müştəri köməkçisi) mövcuddur — fərqli məhsuldur, adların oxşarlığına diqqət et.
