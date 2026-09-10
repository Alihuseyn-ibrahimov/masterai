# MasterAI — dizayn kətanı (mənbə fayllar)

Bu qovluq dizayn maketlərinin **mənbəyidir**. Yığılmış kətan faylı
(`masterai-dizayn.html`, ~2.5 MB) repoda saxlanmır — bu fayllardan
yenidən yaradılır.

## Artboard-lar

| Fayl | Ekran | Ölçü |
|---|---|---|
| `Main.dc.html` | Açılış səhifəsi | 1440×1180 |
| `MuellimKonsol.dc.html` | Müəllim konsolu | 1440×900 |
| `TelebeAna.dc.html` | Tələbənin ana ekranı | 390×844 |
| `SualHell.dc.html` | Sual həlli | 390×844 |
| `Nailiyyetler.dc.html` | Nailiyyətlər | 390×844 |

`canvas.json` yerləşməni və qeydləri saxlayır.

## Mövcud sistemlə əlaqə

Bütün rənglər, şrift ölçüləri və boşluqlar `web/assets/css/tokens.css`-dən
BİRBAŞA götürülüb — yeni rəng uydurulmayıb. Maketlər `.dc.html`
formatında müstəqil fayllardır, ona görə CSS dəyişənləri deyil, hərfi
hex dəyərləri işlədilir.

## Canlı saytdan fərqlər (təsdiq gözləyir)

1. Emoji ikonlar → xətt-əsaslı SVG
2. Fənn rəngi: yalnız kənar xətti deyil — çip + tint + tərəqqi zolağı
3. Tərəqqi halqaları (rəqəm əvəzinə vizual)
4. Cavab variantları 56px hündürlük + hərf nişanı
5. Düzgün/səhv iki dəfə işarələnir (fon + ikon) — rəng korluğu üçün
6. **Yeni element:** gündəlik "silsilə" göstəricisi — hazırkı saytda YOXDUR,
   backend-də yalnız `silsile_5` nişanı var. Təsdiq gözləyir.
