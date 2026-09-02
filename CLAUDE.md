# MasterAI — operativ təlimat

Dövlət qulluğu və magistratura imtahanlarına hazırlaşan tələbələr üçün: dərs
materialını (sayt linki, PDF, şəkil) yükləyir → AI ondan MCQ test sualları
çıxarır → şəxsi/qrup çatında dostlarla birgə canlı "quiz" kimi həll edilir.

**Status: dizayn mərhələsində.** Hələ kod yoxdur. Brainstorming skill-i ilə
alt-sistemlərə bölünüb, birinci "AI sual generasiya pipeline-ı" spesifikasiya
edilir (bax `docs/superpowers/specs/`).

## Arxitektura (planlaşdırılan)

`dildostu/` layihəsinin sınanmış naxışı əsas götürülür (Flutter app + FastAPI
backend, `prdostu.com` alt-domenə DigitalOcean deploy, provider fallback
zənciri).

| Alt-sistem | Nədir | Vəziyyət |
|---|---|---|
| AI sual generasiya pipeline-ı | Material ingestion (sayt/PDF/şəkil) + LangChain LCEL + MCQ çıxarılması | Dizayn edilir |
| Memarlıq + Data modeli | Auth, DB sxemi, FastAPI+Flutter skelet | Planlaşdırılıb |
| Çat infrastrukturu | Şəxsi+qrup çatlar, WebSocket, AI bot iştirakçı | Planlaşdırılıb |
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
