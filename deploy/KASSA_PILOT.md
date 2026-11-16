# Kurs Kassası: demo və Master NR 1 pilotu

Addım 8 (spec: `docs/superpowers/specs/2026-11-15-kurs-kassasi-design.md`).
Bu sənəd iki şeyi verir: görüşdə Kassanı göstərmək üçün demo, və real kursda
4 həftəlik pilotun planı. Real ödəniş datası hələ YOXDUR, ona görə aşağıdakı
bütün rəqəmlər sintetikdir və görüşdə belə də deyilməlidir.

## 1. Demo (15 dəqiqə hazırlıq)

```bash
.venv/bin/python deploy/kassa_demo.py --data-dir /tmp/kassa-demo
set -a; . /tmp/kassa-demo/demo.env; set +a
.venv/bin/uvicorn server.app:app --port 8125
```

Skript BOŞ qovluqda 3 qrup (abituriyent 120, magistr 90, ingilis 70 AZN), 40
uydurma şagird, 6 aylıq ödəniş və xərc yaradır, giriş e-poçtu və şifrəni çap
edir. Qovluqda artıq `.db` varsa heç nə yazmır: canlı bazaya toxuna bilməz.
`demo.env` serverin HƏR bazasını həmin qovluğa yönəldir.

Sayt: `web/`-in surətində `assets/js/config.js`-i `http://127.0.0.1:8125`-ə
yönəlt (repodakı fayla toxunma), `python -m http.server 8123`, giriş →
Hesabatlar → Kassa. Noyabr 16-da yoxlanıb (`--seed 15`):

| Göstərici | Dəyər |
|---|---|
| Gözlənilən / yığılan | 3860 / 2950 AZN (76%, ay yarımdır) |
| Borc | 910 AZN, 10 nəfər |
| 2+ aydır ödəmir («yəqin gedib») | 3 nəfər |
| Xalis (xərc 2450 AZN) | 500 AZN |

### Görüşdə göstərmə sırası (7 dəqiqə)

1. **Dörd kart:** «bu ay nə gözlənilir, nə gəlib». Sahib bunu bu gün dəftərdən
   və ya Excel-dən hesablayır.
2. **Borclular:** yuxarıda 2-3 aydır ödəməyənlər. Sual: «Bu adamlardan neçəsinin
   getdiyini bu gün bilirsiniz?» «Xatırlat» qrup çatına mesaj yazır.
3. **Qəbzi oxu:** «Salam müəllim, Ayselin noyabr pulunu köçürdüm, 120 AZN» yapışdır →
   şagird, ay, məbləğ təklif olunur, «Ödədi» bir kliklə. Qəbz mətni kənar AI-a
   getmir (yalnız qaydalar və ya öz modelimiz).
4. **Qruplar üzrə + 6 ay:** hansı qrup daha pis yığır, xalis nə qədər qalır.
5. **Agentlər (sahibin kompüterində, istəyə görə):** `kassa_agents report` aylıq
   hesabat, `kassa_agents ask "oktyabrda kim ödəməyib?"`. Adlar AI-a getmir.

## 2. Pilot: Master NR 1, 4 həftə

**Məqsəd:** Kassanın real kursda vaxta və pula qənaət etdiyini rəqəmlə göstərmək,
və churn modeli üçün ilk real datanı toplamaq.

| Həftə | Nə edilir | Kim |
|---|---|---|
| 0 | Sahiblə 30 dəq: hazırda ödənişi necə izləyir, ayda neçə saat gedir, keçən ay neçə şagird getdi (BAZA rəqəmləri). Kurs, qruplar, aylıq məbləğlər daxil edilir. | sahib + Alihuseyn |
| 1 | Şagirdlər kodla qoşulur, sahib hər ödənişi «Ödədi» və ya «Qəbzi oxu» ilə qeyd edir. | sahib / administrator |
| 2 | Həftəlik zəng siyahısı (2+ ay və ya uzun gecikmə). Zəngin nəticəsi qeyd olunur: qaldı / getdi / ödədi. | administrator |
| 3 | Aylıq hesabat (agent), xərclər daxil edilir. | sahib |
| 4 | Yekun görüş: ölçülər, rəy, qiymət təklifi. | sahib + Alihuseyn |

**Ölçülər (həftə 0 ilə müqayisə):**

- Ödənişi izləməyə həftədə sərf olunan vaxt (sahibin öz sözü ilə, saat).
- Ayın 15-nə qədər yığım faizi.
- Borcun tapılmasından zəngə qədər gün sayı.
- «Qəbzi oxu»nun real mesajlarda düzgün şagird+ay+məbləğ verdiyi pay
  (yalnız sahibin razılığı ilə, mesajlar saxlanmır, yalnız düz/səhv sayılır).
- Zəng siyahısındakıların neçəsi həqiqətən getdi (precision). 4 həftə bunun üçün
  azdır: sayı hesabatda «ilkin» kimi yazılır.

**Data və məxfilik:** valideyn və şagird adları kursun serverindən çıxmır.
Model üçün ixrac yalnız anonimdir (`ml/churn/schema.py` sütunları, ad yox).
Pilot bitəndə sahib datanın silinməsini istəyə bilər.

**Bilinən məhdudiyyətlər (görüşdə açıq deyilir):**

- Keçmiş ayların ödənişini toplu yükləmək (CSV) hələ yoxdur: pilot cari aydan
  başlayır, tarixçə 4 həftədə yığılır.
- Onlayn kartla ödəniş yoxdur (müqavilə/VÖEN tələb edir).
- Churn modeli sintetik datada «neçə gündür susub» qaydasını keçmir, ona görə
  zəng siyahısı qaydaya əsaslanır. Model real data ilə yenidən yoxlanacaq.
- Qəbz oxuyucusunun QLoRA versiyası Colab-da hələ işlədilməyib.

## 3. Qiymət fərziyyəsi (pilotda yoxlanılır)

Pilot pulsuzdur. Sonra plan sənədindəki (bazar araşdırması) iki paket:
**Start 99 AZN/ay** (50 şagirdə qədər) və **Kurs 249 AZN/ay** (200 şagirdə qədər),
yəni şagird başına təxminən 1-2 AZN. Arqument: vaxtında tapılan bir «itən»
şagird ayda 70-120 AZN-dir, demo kursunda (aylıq gözlənilən 3860 AZN) Start
paketi gəlirin 2.6%-idir və bir-iki şagirdi saxlamaqla özünü ödəyir. Rəqəmlər
fərziyyədir: pilotun yekun görüşündə sahibin cavabına görə dəyişdirilir.
