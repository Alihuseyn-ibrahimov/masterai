# MasterAI — veb (mediapulse.az naxışı)

Bu qovluq Flutter tətbiqini əvəz edir. Səbəb və müqayisə üçün bax
`.planning/2026-09-09-masterai-app-redesign/progress.md`.

**Build addımı YOXDUR.** npm yoxdur, bundler yoxdur, Flutter SDK yoxdur.
Fayllar olduğu kimi nginx tərəfindən verilir — `saas_core` (mediapulse.az)
ilə eyni yanaşma.

## Quruluş

```
web/
  index.html         # açılış səhifəsi (SEO, OG, JSON-LD)
  mexfilik.html      # məxfilik siyasəti
  sertler.html       # istifadə şərtləri
  giris.html         # daxil ol
  qeydiyyat.html     # hesab yarat
  qosul.html         # PIN ilə qoşulma (hesabsız) + canlı sessiya
  chatlar.html       # çat siyahısı
  chat.html?id=N     # çat + quiz (WebSocket)
  tapsiriqlar.html   # ev tapşırıqları siyahısı
  tapsiriq.html?id=N # tapşırığın həlli
  tarixce.html       # nəticə tarixçəsi
  nailiyyetler.html  # nişanlar
  profil.html        # hesab, görünüş, çıxış
  muellim.html       # sual bankları + material yükləmə
  suallar.html?id=N  # sual redaktəsi
  sessiyalar.html    # canlı sessiya (host)
  hesabatlar.html    # ev tapşırığı təyini + hesabatlar
  manifest.json  robots.txt  sitemap.xml
  assets/
    css/  tokens.css · base.css · components.css · landing.css
    js/   config · api · socket · chat-socket · chat-item · chat-view
          live · nav · page-shell · auth-page · subjects · badges
    gallery.html  icon.svg  og-banner.svg
  tests/            # JS vahid testləri (node --test, npm YOX)
```

## Səhifələri açmaq — LOKAL SERVER MƏCBURİDİR

Fayla iki dəfə klikləmək (`file://`) **İŞLƏMİR**: brauzer ES modullarını
CORS səbəbi ilə bloklayır (real Chromium testində təsdiqləndi —
"Access to script ... has been blocked by CORS policy"). Səhifə açılır,
amma boş qalır.

Windows-da:

```powershell
cd "C:\Users\Alihuseyn Ibrahimov\PycharmProjects\Quantum\masterai\web"
py -m http.server 8123
```

Sonra brauzerdə: `http://localhost:8123/giris.html`

Dayandırmaq: terminalda `Ctrl+C`.

**İstisna:** `assets/gallery.html` (dizayn sistemi) JavaScript modulu
işlətmir — ona iki dəfə kliklə də baxmaq olar.

## Pozulmaz qayda

`tokens.css`-dən başqa heç bir CSS faylında birbaşa rəng və ya ölçü
yazılmır — yalnız `var(--...)`. Bu qayda `tests/test_web_design_system.py`
ilə avtomatik yoxlanılır (33 test):

- birbaşa hex/rgb rəng → test sınır
- token adında yazı səhvi (`--color-primry`) → test sınır
- tünd rejimdə unudulmuş rəng → test sınır

Üçü də real mutasiya ilə yoxlanılıb — testlər həqiqətən pozula bilir.

## Niyə ölçülər üçün istisna var

`@media` sorğuları CSS-də `var()` qəbul etmir (dilin məhdudiyyəti).
Kənar xətti/outline enləri (1-3px) də istisnadır — struktur detalıdır,
tokenləşdirmək oxunaqlığı azaldar. Qalan hər şey tokendədir.
