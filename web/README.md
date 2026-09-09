# MasterAI — veb (mediapulse.az naxışı)

Bu qovluq Flutter tətbiqini əvəz edir. Səbəb və müqayisə üçün bax
`.planning/2026-09-09-masterai-app-redesign/progress.md`.

**Build addımı YOXDUR.** npm yoxdur, bundler yoxdur, Flutter SDK yoxdur.
Fayllar olduğu kimi nginx tərəfindən verilir — `saas_core` (mediapulse.az)
ilə eyni yanaşma.

## Quruluş

```
web/
  assets/
    css/
      tokens.css       # YEGANƏ rəng/ölçü mənbəyi
      base.css         # reset, tipoqrafika, layout
      components.css   # kart, düymə, nişan, sahə, hal ekranları
    js/                # (Faza 2+) API client-i və ekran məntiqi
    gallery.html       # bütün komponentlər bir səhifədə
```

## Dizayn sistemini görmək

`web/assets/gallery.html` faylına **iki dəfə klikləyin** — brauzerdə
açılır, server lazım deyil. Sağ yuxarıdakı düymə tünd/işıqlı rejimi
yoxlayır.

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
