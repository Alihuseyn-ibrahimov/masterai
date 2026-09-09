# Tərəqqi

## 2026-09-09 — Audit və plan

Kod bazası üzərində real ölçmə aparıldı (`masterai/app`):

- 21 ekran, 6,359 Dart sətri
- Paylaşılan komponent qovluğu: **yoxdur**
- `NavigationBar`/`BottomNavigationBar`/`TabBar`: **0**
- `MaterialPageRoute`: 26, `Navigator.of(context).push`: 20
- `required this.token`: **19 ekranda**
- Vəziyyət idarəetmə paketi: yoxdur
- `testWidgets` testi: **0** (13 test faylının hamısı data qatı)
- Ən böyük ekran: `chat_screen.dart`, 752 sətir
- `main.dart`-da `kIsWeb` şərti veb istifadəçisini birbaşa müəllim
  konsoluna aparır → **veb-də tələbə axını mövcud deyil**

mobbin.com analiz edilə bilmədi (proksi 403 — real yoxlama; üstəlik
ödənişli, müəllif hüquqlu məzmun). Əvəzinə tanınmış təhsil tətbiqi
naxışları əsas götürüldü, istifadəçi istəsə öz ekran şəkillərini
göndərə bilər.

İstifadəçi qərarları (AskUserQuestion ilə):
- Domen: `masterai.prdostu.com` = sayt, `api.masterai...` = API
- Veb auditoriya: marketinq səhifəsi + giriş → tam tətbiq
- Dizayn dili: Quizlet/Brilliant tərzi (təmiz, ciddi, fokuslu)
- Başlanğıc: əvvəl skelet (marşrutlar + naviqasiya + dizayn sistemi)

**Növbəti:** Faza 1 (dizayn sistemi tokenləri).

## 2026-09-09 — MediaPulse təcrübəsinin araşdırılması

İstifadəçinin təklifi ilə `saas_core/` (mediapulse.az) araşdırıldı.
Planı DƏYİŞƏN bir tapıntı oldu:

**Açılış səhifəsi Flutter-də olmamalıdır.** MediaPulse-un landing-i
server-render HTML-dir; SEO və link önizləməsi məhz buna görə işləyir.
Flutter web məzmunu canvas/DOM-a çəkdiyi üçün Google botu boş səhifə
görür. Yeni quruluş: `/` statik HTML, `/app/` Flutter, `api.` backend.

MediaPulse-da hazır, MasterAI-də tamamilə yox olanlar: SEO meta,
Open Graph/Twitter Card, JSON-LD, robots.txt, sitemap.xml, PWA
manifest + service worker, og-banner, məxfilik/şərtlər səhifələri,
testlə qorunan deploy skripti.

Open Graph MasterAI üçün MediaPulse-dan da vacibdir — canlı sessiya
PIN linki qrup çatlarında paylaşılır, önizləməsiz link etibarsız
görünür.

Plan 8 fazadan 9-a çıxdı (SEO/PWA paketi ayrıca faza oldu).

## 2026-09-09 — VEB-FIRST-Ə KEÇİD (arxitektura qərarı)

İstifadəçi Flutter-in ləğvini təklif etdi. Faktlar yoxlanıldı və qərar
təsdiqləndi:

**Həlledici fakt:** Flutter app-ın release imzalama açarı yoxdur
(`build.gradle.kts` debug açarları ilə işləyir, `app/README.md`-də
sənədləşib) və Play Store-a heç vaxt dərc olunmayıb. Yəni **bu tətbiq
real tələbəyə çata bilmir** — bütün testlər tərtibatçının öz
emulyatorunda və Chrome-da olub. Sayt isə link paylaşılan an işləyir.

**İkinci arqument:** plan onsuz da 21 ekranın HAMISINI yenidən yazmağı
nəzərdə tuturdu (Faza 5), ona görə keçidin ƏLAVƏ xərci göründüyündən
qat-qat azdır — eyni iş, fərqli dildə.

**Backend toxunulmur:** 540 test, REST+WebSocket, Flutter-ə heç bir
bağlılığı yoxdur. İtən yalnız UI qatıdır (6,359 sətir), qazanılan real
paylanma + hər səhifə üçün SEO + tək texnologiya.

`app/` SİLİNMİR — "arxiv, əvəzlənib" qeydi ilə repoda qalır.

Texniki yanaşma: statik HTML + CSS + vanilla JS, mövcud JWT API-ni
çağırır. npm yox, bundler yox, build addımı yox — `saas_core`
(mediapulse.az) ilə eyni yanaşma.

### Faza 1 TAMAMLANDI — dizayn sistemi

`web/assets/css/tokens.css` (yeganə rəng/ölçü mənbəyi), `base.css`,
`components.css`, `gallery.html` (bütün komponentlər bir səhifədə,
build tələb etmir).

Palitra Flutter-dən köçürüldü ki, davamlılıq itməsin: toxum rəngi
`#2F6FED`, 6 fənn aksenti `app_subject_colors.dart`-dan. Tünd rejim
həm sistem seçimi (`prefers-color-scheme`), həm əl ilə (`data-theme`).

**`tests/test_web_design_system.py` — 33 test.** MediaPulse-da CSS
dəyişənləri konvensiya idi; burada testlə möhkəmləndirilir. Üç qayda
real mutasiya ilə yoxlanıldı (test poza bilməyən test dəyərsizdir):

| Pozuntu | Nəticə |
|---|---|
| `background: #FF0000` | ✅ test sındı |
| `var(--color-primry-hover)` (yazı səhvi) | ✅ test sındı |
| tünd rejimdə bir token unuduldu | ✅ test sındı |

Bütün dəst: **540 test keçir** (əvvəlki 507 + 33 yeni).

**Növbəti:** Faza 2 — API client-i (`assets/js/api.js`) + giriş/qeydiyyat
səhifələri, mövcud JWT backend-inə qarşı.

### Faza 2 TAMAMLANDI — API client-i + auth səhifələri

`web/assets/js/api.js` mövcud JWT backend-inə qarşı işləyir (backend
DƏYİŞMƏYİB). `config.js` backend ünvanlarının tək mənbəyidir — Faza 9-da
API subdomenə köçəndə yalnız o fayl dəyişəcək.

Səhifələr: `giris.html`, `qeydiyyat.html` + müvəqqəti `hesabim.html` /
`muellim.html` (giriş axınının real backend-lə işlədiyini sübut etmək
üçün; Faza 3-də əvəzlənəcək).

**Veb-first keçidinin ilk konkret qazancı:** frontend məntiqini İNDİ
ÖZÜM icra edə bilirəm. Flutter kodunu bu mühitdə ümumiyyətlə işə salmaq
mümkün deyildi (SDK yoxdur) — hər şey istifadəçinin kompüterində
yoxlanılırdı. Node 22 mövcuddur, `node --test` npm quraşdırma tələb
etmir.

Yazılarkən qarşısı alınan real problemlər:

- **FastAPI 422 `detail` SİYAHIDIR** (obyekt deyil) — birbaşa göstərsək
  istifadəçi "[object Object]" görərdi
- **`localStorage` ata bilər** (Safari gizli rejimi, kuki bloklanması) —
  yaddaş ehtiyatı əlavə olundu, tətbiq sınmır
- **Şəbəkə xətası ilə HTTP xətası fərqləndirilir** (`status=0`) —
  Flutter tərəfində geniş `catch (_)` CORS problemini gizlətmişdi
- **nginx 502 gövdəsi HTML olur** — `response.json()` atır, idarə edilir
- **Sınıq linklər** — test `index.html` və `qosul.html`-a olan linkləri
  tutdu (o səhifələr hələ yoxdur), linklər çıxarıldı

Testlər: 574 pytest (əvvəlki 541 + 33) + 18 JS testi. Endpoint müqaviləsi
testi mutasiya ilə yoxlanıldı (`/auth/loginn` → sındı).

**Növbəti:** Faza 3 — çat siyahısı və çat ekranı (WebSocket).

### Faza 3 TAMAMLANDI — çat siyahısı + çat (WebSocket)

Backend protokolu `server/app.py` və `server/quiz_runner.py`-dən oxundu,
güman edilmədi. Ən incə yer: **eyni məntiqi element iki fərqli formada
gəlir** — tarixçədə `content` JSON SƏTRİDİR, canlı hadisədə sahələr ən
üst səviyyədədir və id `message_id` adlanır. Üstəlik `quiz_finished`
tarixçədə `kind:"system"` kimi saxlanılır, əsl növ JSON-un içindədir.
`chat-item.js` hər ikisini tək şəklə çevirir; test bunu birbaşa
yoxlayır ("EYNİ element tarixçədən və canlıdan eyni şəklə gəlir").

Flutter-in üç sənədləşmiş məhdudiyyəti düzəldildi:

| Flutter-də | İndi |
|---|---|
| WebSocket avtomatik yenidən qoşulma YOX idi | Eksponensial gözləmə + jitter; fatal kodlarda (4401/4403/4404) qəsdən dayanır |
| Adlar "İstifadəçi #3" kimi görünürdü | `GET /chats/{id}/members` ilə real adlar |
| Cavablanmış sual kartı aktiv qalırdı | `answeredQuestionIds` ilə bloklanır |

Yenidən qoşulma dedupe tələb edir: qoşulan kimi server tarixçəni TƏKRAR
göndərir. `upsertItem` eyni `id`-li elementi əvəz edir.

Testdə tapılan real səhv: `computeBackoffDelay` üst həddi 10% aşırdı
(30s əvəzinə 33s) — jitter yalnız eksponensial hissəyə tətbiq olunurdu.
Hədd son nəticəyə keçirildi.

Təhlükəsizlik: çat məzmununu başqa istifadəçilər yazır, ona görə bütün
istifadəçi mətni `textContent` ilə qoyulur, `innerHTML` işlədilmir.

581 pytest + 62 JS testi keçir.

**Növbəti:** Faza 4 — naviqasiya çərçivəsi + marşrutlar, yaxud müəllim
konsolu (istifadəçinin seçimi).

### Faza 5-9 TAMAMLANDI (avtonom iş, istifadəçi yatarkən)

**Faza 5 — bütün ekranlar real məzmunla:**
muellim.html (material yükləmə + bank siyahısı, 10 san avtomatik
yenilənmə), suallar.html (redaktə/silmə), sessiyalar.html (PIN, vaxt
büdcəsi, iştirakçı tərəqqisi), qosul.html (hesabsız PIN qoşulması),
tapsiriqlar.html + tapsiriq.html (ev tapşırığının həlli), tarixce.html,
nailiyyetler.html, hesabatlar.html.

Yenidən qoşulma məntiqi `socket.js` bazasına çıxarıldı — çat, host və
oyunçu soketləri onu paylaşır. Refaktordan sonra mövcud testlərin
hamısı keçdi.

**Faza 6-7 — açılış səhifəsi + SEO/PWA:**
Statik HTML landing (hero → nə edir → necə işləyir → kimə lazımdır →
FAQ → CTA), OG/Twitter/JSON-LD, robots.txt, sitemap.xml, PWA manifest,
məxfilik və istifadə şərtləri.

Məxfilik siyasətində ən vacib bənd açıq yazıldı: material mətni sual
hazırlamaq üçün xarici LLM provayderlərinə göndərilir. Hər iki hüquqi
səhifədə "sahibkarın nəzərdən keçirməsi lazımdır" xəbərdarlığı var.

**Faza 9 hazırlığı — nginx + deploy:**
Statik sayt və API eyni domeni paylaşacaq; ayırma nginx-də yol kökünə
görədir. İki gizli risk testlə bağlandı:
1. Backend-ə yeni üst səviyyəli endpoint əlavə edilib nginx siyahısına
   yazılmasa, istifadəçi 404 alar (yalnız production-da görünərdi).
2. nginx-də REGEX location prefiks location-dan üstündür — `ws` regex
   siyahısına düşsə WebSocket upgrade başlıqları itər və handshake
   SÜKUTLA sınar.

`deploy_web.ps1` saas_core-un test qapısı naxışını təkrarlayır, üstəlik
disk yoxlaması var (bu VPS-də disk dolması əvvəllər dörd servisi riskə
atıb).

**Yekun yoxlama:** 17 səhifənin hamısı real Chromium-da JS xətası
olmadan yüklənir (`check_pages_in_browser.py`).

750 pytest + 106 JS testi keçir.

**İstifadəçini gözləyən işlər:** DNS qeydi, nginx quraşdırılması,
certbot, ilk deploy, real backend-lə uc-uca sınaq.
