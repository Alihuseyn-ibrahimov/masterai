# İmplementasiya planı — dizayn yenilənməsi + domen

**Spec:** `docs/superpowers/specs/2026-09-09-masterai-redesign-and-domain-design.md`
**Başlanğıc:** 2026-09-09

Hər fazanın sonunda İSTİFADƏÇİNİN öz Windows mühitində
`flutter analyze` (0 xəta) + `flutter test` (hamısı keçir) MƏCBURİDİR —
bu sandbox-da Flutter SDK yoxdur, kod yalnız yazıla bilər, icra edilə
bilməz (bax `masterai/CLAUDE.md`, "Dərs: Flutter app SDK-sız yazıldı").

---

## Faza 1 — Dizayn sistemi (tokenlər)

**Nə:** `lib/src/theme/` genişlənir — `app_spacing.dart` (4-lük şkala),
`app_radius.dart`, `app_typography.dart`, `app_theme.dart` (`main.dart`-dakı
tema qurulması ora köçür).

**Niyə əvvəl bu:** komponentlər tokenlərin üzərində qurulur; əks
ardıcıllıqda hər komponentə sonradan toxunmaq lazım gələr.

**Bitmə şərti:** `main.dart` 40 sətirdən qısa; tema testləri keçir;
ekranlarda GÖRÜNÜŞ dəyişmir (yalnız struktur).

---

## Faza 2 — Komponent kitabxanası

**Nə:** `lib/src/widgets/` — `AppScaffold`, `AppCard`, `AppButton`,
`AppTextField`, `SectionHeader`, `StatTile`, `SubjectChip`, `ProgressBar`,
`AppAvatar`, `EmptyState`, `ErrorState`, `LoadingState`.

**Niyə vacib:** hazırda paylaşılan komponent qovluğu YOXDUR — 21 ekran
öz düymə/kartını ayrıca qurur, uyğunsuzluğun kök səbəbi budur.

**Bitmə şərti:** hər komponent üçün `testWidgets` testi (tətbiqdə ilk
widget testləri); ekranlar hələ köçürülmür.

---

## Faza 3 — `SessionScope` (prop drilling ləğvi)

**Nə:** `InheritedNotifier` əsaslı sessiya konteyneri; 19 ekrandan
`token`/`userId`/`displayName`/`isTeacher`/`isAdmin` konstruktor
parametrləri silinir.

**Niyə marşrutlardan ƏVVƏL:** `go_router`-in marşrut mühafizəsi
(tokensiz istifadəçini `/giris`-ə yönləndirmək) sessiyanı mərkəzi
yerdən oxumağı tələb edir. Əks ardıcıllıqda marşrutlar iki dəfə yazılır.

**Bitmə şərti:** `grep -c "required this.token" lib/` → 0;
`flutter test` keçir; tətbiq davranışı DƏYİŞMİR.

---

## Faza 4 — `go_router` + naviqasiya qabığı

**Nə:** spec-dəki marşrut xəritəsi, `ShellRoute` ilə davamlı qabıq
(dar: `NavigationBar`, geniş: `NavigationRail`), rol əsaslı bölmələr,
marşrut mühafizəsi, `kIsWeb` şərtinin ləğvi.

**Niyə:** URL olmadan "əsl sayt" mümkün deyil — brauzerin geri düyməsi,
link paylaşımı, əlfəcin heç biri işləmir.

**Bitmə şərti:** brauzerdə `/chatlar` yazıb birbaşa açmaq işləyir; geri/
irəli düymələri işləyir; tələbə veb-də tələbə ekranlarını görür (indiki
kimi müəllim konsoluna atılmır).

**Bu faza SKELETİN SONUDUR** — istifadəçinin seçdiyi başlanğıc nöqtəsi
buraya qədərdir.

---

## Faza 5 — Ekranların köçürülməsi (4 alt-addım)

| 5a | Auth + açılış | `login`, `register` |
| 5b | Tələbə əsas axını | `chat_list`, `chat` (752 sətir — bölünür), `homework_*` |
| 5c | Tələbə tarixçə/nişan | `my_history`, `student_history`, `my_badges`, `leaderboard` |
| 5d | Müəllim + admin | `host_*`, `question_*`, `homework_teacher_*`, `admin_*` |

Hər alt-addım ayrıca yoxlanılır — bir dəfəyə hamısını dəyişmək
reqressiyanı tapılmaz edər.

---

## Faza 6 — Marketinq açılış səhifəsi (`/`)

**Nə:** məhsulu izah edən səhifə (nə edir, kimə lazımdır, necə işləyir,
"Daxil ol"/"Qeydiyyat"/"PIN ilə qoşul"). İstifadəçinin seçimi.

---

## Faza 7 — Responsiv cilalama

**Nə:** maksimum məzmun genişliyi (geniş ekranda mətn sonsuz uzanmır),
klaviatura naviqasiyası, fokus göstəriciləri, hover halları, `<title>`
və favicon.

---

## Faza 8 — Domen (`api.masterai.prdostu.com` + statik sayt)

Bu faza **istifadəçi tərəfindən VPS-də** aparılır, mən əmrləri və
konfiqurasiyanı hazırlayıram.

1. Cloudflare-də `api.masterai` A qeydi → VPS IP
2. nginx: mövcud fayl iki server blokuna bölünür
3. `certbot --nginx -d api.masterai.prdostu.com`
4. `config.dart` yenilənir → yeni mobil/veb build
5. Windows-da `flutter build web --release` → `scp` ilə VPS-ə
   (**əvvəlcə `df -h /`** — disk 97.4% doludur)
6. n8n workflow-un `/admin/stats` URL-i yenilənir
7. `DEPLOY.md` yenilənir

**Qeyd:** bu faza texniki olaraq 1-7-dən ASILI DEYİL — istifadəçi
istəsə istənilən vaxt paralel apara bilər.

---

## Əhatə xaricində (qəsdən)

- Backend API dəyişiklikləri (dizayn işi backend-ə toxunmur)
- Yeni funksiyalar (yalnız mövcud 21 ekran yenidən qurulur)
- Dostluq UI-ı (MVP-dən bəri bilinən boşluqdur, ayrıca iş)
- İngestion keyfiyyəti (ayrıca, davam edən iş — aşağı bax)

## Paralel gedən açıq iş (dizayndan asılı deyil)

1. Yeni sual bankının keyfiyyət yoxlaması (xətt təmizləməsindən sonra)
2. `llm_ok` jurnal yoxlaması — Claude fallback-ı real emalda işləyirmi
3. Dəyişiklik tarixçəsi bölməsinin ölçülməsi/təmizlənməsi
4. Emal yarımçıq qalanda "Hazırlanır…" vəziyyətində ilişmə (bilinən,
   düzəldilməmiş etibarlılıq boşluğu)
