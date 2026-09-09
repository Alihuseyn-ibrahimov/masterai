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
