# MasterAI — Flutter App (ARXİV — əvəzlənib)

> **⚠️ Bu tətbiq artıq inkişaf etdirilmir.** 2026-09-09-da veb-first
> arxitekturaya keçildi (`masterai/web/`). Kod SİLİNMİR — gələcəkdə
> native mobil tətbiq lazım olsa, işlək baza kimi qalır.
>
> **Keçidin səbəbi (bir cümlə):** bu tətbiqin release imzalama açarı
> yoxdur və Play Store-a heç vaxt dərc olunmayıb — yəni real tələbəyə
> çatmaq üçün paylanma yolu YOXDUR; sayt isə link paylaşılan an işləyir.
> Üstəlik planın Faza 5-i onsuz da 21 ekranın hamısını yenidən yazmağı
> nəzərdə tuturdu, ona görə keçidin əlavə xərci azdır.
>
> Tam müqayisə və qərar: `.planning/2026-09-09-masterai-app-redesign/progress.md`
>
> **Backend TOXUNULMAYIB** — `server/` və `pipeline/` dəyişmədi.

---


Dövlət qulluğu/magistratura imtahanına hazırlaşanlar üçün: dərs materialı
yüklə → AI test sualları çıxarsın → dostlarla (qrup çatında) birgə canlı
quiz kimi həll et.

**Backend:** `https://masterai.prdostu.com` (canlı, `masterai/DEPLOY.md`-yə
bax) — bu app-da ayrıca konfiqurasiya lazım deyil, `lib/src/config.dart`-da
sabit yazılıb.

## Vəziyyət: uc-uca real mühitdə təsdiqlənib

Bu app Claude tərəfindən Flutter SDK-sı OLMAYAN bir mühitdə yazılıb, sonra
istifadəçinin öz Windows mühitində (`flutter analyze`/`test`/`run`, real
Android emulyator) tam yoxlanılıb. `flutter analyze` — 0 xəta, `flutter
test` — 26/26, `flutter run` — real backend-lə (qeydiyyat → qrup çatı →
mesajlaşma → material yükləmə → AI sual generasiyası → quiz həlli)
uc-uca işlədi (bax `.planning/2026-09-03-masterai-flutter-app/progress.md`
üçün tam sınaq jurnalı, o cümlədən yol boyu tapılıb düzəldilmiş real
bug-lar — `masterai/CLAUDE.md`-nin "Dərs" bölmələri).

## İşə salma

```bash
cd masterai/app
flutter pub get
flutter analyze          # statik xəta yoxlaması — İLK BUNU İŞLƏT
flutter test              # data qatı unit testləri
flutter run                # real cihaz/emulator-da
```

`flutter analyze` mütləq təmiz çıxmalıdır (əks halda kodda tip/import
səhvi var). `flutter test` data qatını (auth/chat/material/quiz client-ləri
+ `ChatItem` JSON parsing) yoxlayır — UI widget testləri bu fazada YOXDUR
(vaxt/effort balansı, MVP-nin əhatəsindən kənar buraxılıb).

## Bilinən məhdudiyyətlər (MVP, qəsdən əhatə xaricində)

- **Dostluq idarəetməsi UI-ı yoxdur** — backend-də `POST /friends/requests`
  və s. hazırdır, amma app-da ekran yoxdur. Nəticə: `direct` (şəxsi) çat
  yaradıla BİLMİR (backend dostluq tələb edir) — yalnız **qrup çatları**
  işləyir. Solo/qrup test axını (öz-özünə qrup yarat → material yüklə →
  quiz həll et) tam funksionaldır.
- **WebSocket avtomatik yenidən qoşulma yoxdur** — bağlantı kəsilsə
  (`ChatScreen`-in narıncı zolağı görünər) istifadəçi çatdan çıxıb yenidən
  girməlidir.
- **İstifadəçi adı göstərilmir mesaj/quiz kartlarında** — `sender_id`/
  `user_id` rəqəm kimi göstərilir ("İstifadəçi #3"), çünki app-da
  istifadəçi-ID→ad kataloqu yoxdur (backend-də belə bir endpoint də yoxdur
  hələ). Kosmetik məhdudiyyət, funksionallığı poza bilmir.
- **İmzalama (release keystore) yoxdur** — `build.gradle.kts` debug
  açarları ilə release build edir (`flutter run --release` işləsin deyə),
  Play Store dərci üçün öz keystore-unuzu əlavə etməlisiniz.

## Struktur

```
lib/
  main.dart              # root + saxlanmış sessiya yoxlaması
  src/
    config.dart           # backend ünvanları
    models/                # backend JSON-una uyğun modellər
      chat_item.dart        # ən mürəkkəb — WS history/canlı hadisə normalizasiyası
    data/                   # REST/WebSocket client-ləri
    ui/                     # ekranlar
test/                    # data qatı unit testləri (MockClient)
```
