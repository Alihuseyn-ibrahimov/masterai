# MasterAI — tətbiq dizaynının və domen arxitekturasının yenilənməsi

**Tarix:** 2026-09-09
**Status:** Təsdiqlənmiş dizayn qərarları, implementasiya planı `.planning/2026-09-09-masterai-app-redesign/`

## 1. Problem

İstifadəçinin qiymətləndirməsi: *"tətbiqimizin real app kimi görünüşü və
arxitekturası çox səliqəsizdir"*. Bu, subyektiv təəssürat deyil — kod
bazasında ölçülə bilən səbəbləri var.

### Auditin nəticələri (2026-09-09, `masterai/app` üzərində real ölçmə)

| Göstərici | Dəyər | Nə demədir |
|---|---|---|
| Ekran sayı | 21 | — |
| Dart sətri | 6,359 | — |
| Paylaşılan komponent qovluğu | **yoxdur** | Hər ekran öz düymə/kart/boş-hal görünüşünü ayrıca qurur → vizual uyğunsuzluq |
| `BottomNavigationBar`/`NavigationBar`/`TabBar` | **0** | Tətbiqdə davamlı naviqasiya qabığı yoxdur; hər yerə `push` ilə gedilir, geri qayıtmaq yeganə yoldur |
| `MaterialPageRoute` istifadəsi | 26 | URL yoxdur → veb-də hər səhifə eyni ünvandır, geri/irəli düyməsi və link paylaşımı işləmir |
| `required this.token` konstruktor parametri | 19 | Sessiya məlumatı 19 ekrana ƏL İLƏ ötürülür (prop drilling) — yeni ekran əlavə etmək zəncirvari dəyişiklik tələb edir |
| Vəziyyət idarəetmə paketi | **yoxdur** | Yuxarıdakının səbəbi |
| Widget testi (`testWidgets`) | **0** | 13 test faylının hamısı data qatıdır; UI reqressiyası testlə tutulmur |
| Ən böyük ekran | `chat_screen.dart` — 752 sətir | Bir faylda çox məsuliyyət |
| `lib/src/ui/` kökündə sərbəst fayl | 5 (6 alt-qovluq yanında) | Qovluq strukturu yarımçıq |

### Ən kritik nəticə

`main.dart`-da `kIsWeb` şərti veb istifadəçisini **birbaşa müəllim
konsoluna** aparır. Yəni `masterai.prdostu.com`-a girən tələbə üçün
tətbiq praktiki olaraq mövcud deyil. "Əsl sayt" tələbinin qarşısındakı
əsas maneə budur.

## 2. Mobbin haqqında — açıq qeyd

İstifadəçi mobbin.com-un analiz edilməsini istədi. **Bunu edə bilmirəm**
və səbəbini gizlətmirəm:

1. Bu iş mühitindən mobbin.com-a çıxış proksi tərəfindən bloklanır
   (real yoxlama: `CONNECT tunnel failed, response 403`)
2. Mobbin ödənişli, giriş tələb edən kitabxanadır və məzmunu başqa
   şirkətlərin müəllif hüquqlu ekran şəkilləridir — onları toplu
   çıxarmaq düzgün olmazdı

Əvəzinə iki real yol var və hər ikisi açıqdır:

- **Bu sənədin əsası:** təhsil tətbiqlərinin geniş tanınan dizayn
  naxışları (Quizlet, Brilliant, Khan Academy, Duolingo, Kahoot) —
  konkret qaydalar aşağıda, "3. Dizayn dili" bölməsində
- **İstifadəçi istəsə:** bəyəndiyi ekranların şəkillərini göndərir,
  strukturu təhlil edilib tətbiq olunur

## 3. Dizayn dili — "təmiz, ciddi, fokuslu" (Quizlet/Brilliant tərzi)

İstifadəçi tərəfindən seçilib. Auditoriya dövlət qulluğu/magistratura
imtahanına hazırlaşan **yetkin** insanlardır — oyunlaşdırma var, amma
uşaq tətbiqi kimi görünmür.

### Qərarlar

**Fon və dərinlik.** Ağ/çox açıq boz fon, kartlar kölgə ilə yox, incə
kənar xətti (`outlineVariant`) ilə ayrılır. Tünd rejimdə əksi. Kölgə
yalnız üzən elementlərdə (FAB, dialoq).

**Tipoqrafika.** Mövcud Nunito (başlıq) + Inter (mətn) seçimi SAXLANILIR —
bu cütlük artıq real mühitdə Azərbaycan hərfləri ilə yoxlanılıb. Əlavə
olunan: sabit ölçü şkalası (`AppTypography`), hər ekranda bir dənə əsas
başlıq, alt başlıqlar `titleMedium`-dan böyük olmur.

**Rəng.** `ColorScheme.fromSeed` struktur rəngləri toxunulmaz qalır.
Fənn aksent rəngləri (`AppSubjectColors`, 6 ədəd) yalnız **məzmunu
işarələmək** üçün: fənn nişanı, tərəqqi zolağı, kart kənarı. Düymə
rəngi kimi işlədilmir — əks halda tətbiq alabəzək görünür.

**Boşluq.** 4-lük şkala (4/8/12/16/24/32/48). Ekran kənarı 16, kartlar
arası 12, bölmələr arası 24. Hazırda bu dəyərlər hər faylda əl ilə
yazılıb və uyğun gəlmir.

**Radius.** Kart 16, düymə 12, çip 999 (tam yuvarlaq), sahə 12.

**Hərəkət.** Mövcud "enerjili" animasiyalar (canlı sessiya/həll
ekranları) qalır — onlar real testdə təsdiqlənib. Yeni animasiya yalnız
vəziyyət dəyişikliyini izah edəndə əlavə olunur.

**Boş və xəta halları.** Hazırda çoxu sadə `Text` mesajıdır. Hər siyahı
üçün üç hal məcburidir: yüklənir / boş (nə etmək lazımdır izahı ilə) /
xəta (təkrar cəhd düyməsi ilə).

## 4. Arxitektura qərarları

### 4.1 Sessiya vəziyyəti — `SessionScope` (yeni asılılıq YOX)

19 ekrana `token`/`userId`/`displayName`/`isTeacher`/`isAdmin`
ötürülməsi `InheritedNotifier` əsaslı `SessionScope` ilə əvəz olunur.

**Niyə provider/riverpod/bloc DEYİL:** bu tətbiqin vəziyyəti bir
sessiya obyektidir; xarici paket əlavə etmək öyrənmə/versiya yükü
gətirər, Flutter-in öz mexanizmi tam kifayətdir. Layihənin əvvəlki
qərarları da eyni prinsipdədir (`ThemeExtension` işlədilib, xarici
tema paketi yox).

### 4.2 Marşrutlaşdırma — `go_router`

Bu, **yeni asılılıq tələb edən yeganə qərardır** və səbəbi konkretdir:
"əsl sayt" olmaq üçün URL lazımdır. `Navigator.push` ilə bu mümkün
deyil.

Marşrut xəritəsi (Azərbaycan dilində ünvanlar — istifadəçiyə görünür):

| URL | Ekran | Kim |
|---|---|---|
| `/` | Açılış (marketinq) səhifəsi | Hamı |
| `/giris`, `/qeydiyyat` | Auth | Hamı |
| `/chatlar`, `/chatlar/:id` | Çat siyahısı / çat | Tələbə+müəllim |
| `/tapsiriqlar`, `/tapsiriqlar/:id` | Ev tapşırıqları | Tələbə |
| `/tarixce`, `/nailiyyetler` | Tarixçə, nişanlar | Tələbə |
| `/qosul`, `/qosul/:pin` | PIN ilə sessiyaya qoşulma | Hesabsız |
| `/muellim/*` | Sual bankı, sessiya, hesabatlar, redaktə | Müəllim |
| `/admin/muellimler` | Müəllim idarəetməsi | Admin |

Marşrut mühafizəsi: giriş tələb edən yola tokensiz gedən `/giris`-ə,
müəllim yoluna gedən tələbə `/chatlar`-a yönləndirilir.

### 4.3 Naviqasiya qabığı

`ShellRoute` ilə davamlı qabıq: dar ekranda `NavigationBar` (alt),
geniş ekranda `NavigationRail` (yan). Bölmələr rola görə dəyişir —
tələbə: Çatlar / Tapşırıqlar / Tarixçə / Profil; müəllim: Sual bankları /
Sessiyalar / Hesabatlar / Profil.

### 4.4 Komponent kitabxanası — `lib/src/widgets/`

`AppScaffold`, `AppCard`, `AppButton` (primary/secondary/ghost),
`AppTextField`, `SectionHeader`, `StatTile`, `SubjectChip`,
`ProgressBar`, `AppAvatar`, `EmptyState`, `ErrorState`, `LoadingState`.
Hər biri üçün widget testi — hazırda tətbiqdə **sıfır** widget testi var.

## 5. Domen arxitekturası

Seçilmiş variant: **sayt kök subdomendədir, API ayrılır.**

```
masterai.prdostu.com          → statik Flutter web (nginx root)
api.masterai.prdostu.com      → FastAPI backend (127.0.0.1:8110 proxy)
wss://api.masterai.prdostu.com/ws/...  → WebSocket
```

### Nəyə toxunur

| Yer | Dəyişiklik |
|---|---|
| DNS (Cloudflare) | `api.masterai` üçün yeni A qeydi → VPS IP |
| nginx | İki server bloku: statik sayt + API proxy (mövcud fayl bölünür) |
| certbot | Yeni subdomen üçün sertifikat |
| `app/lib/src/config.dart` | `kApiBaseUrl`/`kWsBaseUrl` → `api.masterai...` |
| Mobil app | Yeni build tələb olunur (köhnə buildlər köhnə ünvana gedəcək) |
| n8n workflow | `/admin/stats` URL-i yenilənir |
| `DEPLOY.md` | Yeni quruluş sənədləşir |
| CORS | **Dəyişiklik yoxdur** — `allow_origins=["*"]` onsuz da açıqdır |

### Kritik məhdudiyyət: build VPS-də EDİLƏ BİLMƏZ

VPS-də Flutter SDK yoxdur, RAM 512 MB, disk **97.4% dolu** (8.65 GB-dan).
Flutter web build-i istifadəçinin Windows mühitində aparılır, `build/web`
qovluğu VPS-ə `scp` ilə köçürülür. Bu, `agent.py`-nin yerləşdirilməsi ilə
eyni naxışdır (bax kök `CLAUDE.md`).

**Disk riski:** bu VPS-də əvvəllər disk dolması `masterai`-ni çökdürüb və
`masternr1` (aktiv pilot) daxil dörd servisi riskə atıb (bax
`masterai/CLAUDE.md`, "Dərs: real deploy tələləri", bənd 6). Fayl
köçürməzdən əvvəl `df -h /` MƏCBURİDİR.

## 6. Risklər

| Risk | Təsir | Qarşısını alma |
|---|---|---|
| VPS diski dolur | Dörd servis birdən düşür | Hər köçürmədən əvvəl `df -h /`; build ~15-30 MB |
| Köhnə mobil buildlər köhnə API ünvanına gedir | İstifadəçi "bağlantı xətası" görür | Köhnə domen bir müddət API-ni proxy etməyə davam edir (kəsmə yox, keçid) |
| 21 ekranın köçürülməsi reqressiya yaradır | İşləyən funksiyalar sınır | Hər fazada `flutter analyze` + `flutter test`, ekran qrupları üzrə addım-addım |
| `go_router` mövcud `Navigator.push` axını ilə toqquşur | Naviqasiya sınır | Faza 4-də hamısı BİR DƏFƏYƏ köçürülür, qarışıq vəziyyət saxlanılmır |
| Dizayn işi backend problemlərini kölgədə qoyur | İngestion keyfiyyəti yarımçıq qalır | Sual bankı keyfiyyət yoxlaması ayrıca izlənilir (bax `progress.md`) |
