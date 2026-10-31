# Real sınaq siyahısı (MasterAI Classroom, gün 14)

İki hissə: əvvəlcə serverdə **avtomatik** yoxlama (5 dəqiqə), sonra yalnız
insanın görə biləcəyi **əl ilə** addımlar.

## 1. Avtomatik (serverdə)

```bash
cd /opt/masterai
export MASTERAI_EMAIL=<müəllim e-poçtu> MASTERAI_PASSWORD=<şifrə>
.venv/bin/python deploy/diagnostics/classroom_smoke.py            # dərs zənciri, real AI ilə
.venv/bin/python -m evals.run --live --judge --out /root/eval-$(date +%F).json   # AI keyfiyyəti
```

`classroom_smoke.py` ayrıca «[Yoxlama] Smoke sinfi» yaradır və real
tələbələrin sinfinə toxunmur: dərs yaradır, başladır, LiveKit tokeni, QR,
lövhə şəkli → OCR, quiz + konspekt, AI yoxlama komandası, AI tutor, dərsi
bitirir. Konspekt dərc olunmur, tapşırıq təyin olunmur. Hər addım ✔/✘ ilə
yazılır, hamısı keçsə çıxış kodu 0. Telefonda yazılmış səslə Whisper-i də
yoxlamaq üçün: `--audio /root/ders.m4a`.

## 2. Əl ilə (yalnız insan görür)

| # | Addım | Gözlənilən |
|---|---|---|
| 1 | Müəllim noutbukdan onlayn dərsi başladır, tələbə **telefondan** `dars.html`-ə girir | Hər ikisi bir-birini görür və eşidir, ekran paylaşımı tələbədə görünür |
| 2 | Müəllim «Səsi yaz», 6+ dəqiqə danışır, «Dərsi bitir» | «Dərs mətni»ndə iki hissə, Azərbaycan dilində oxunaqlı mətn |
| 3 | Sinif dərsində proyektorda «QR davamiyyət», tələbə **telefon kamerası** ilə skan edir | Tələbə girişdən sonra dərs səhifəsinə qayıdır, «N / M» artır |
| 4 | QR şəklini dosta göndər, 1 dəqiqə sonra açsın | «Kod köhnəlib» xətası |
| 5 | Real lövhənin telefon şəkli → «Lövhə şəkli əlavə et» | Mətn «Lövhədən:» başlığı ilə, ə/ö/ü düzgün |
| 6 | «Dərs mətni» → quiz + konspekt → «Tələbələrə göndər» | Tələbə `dersim.html`-də konspekti və quizi görür |
| 7 | Tələbə dərs səhifəsindən «AI tutor», dərsdən bir sual + «Məni yoxla» | Mənbəli cavab [1], materialda olmayan suala «tapmadım» |
| 8 | `suallar.html` → «AI ilə yoxla» | Problemli suallarda qeyd, «Təklifi tətbiq et» işləyir |
| 9 | Claude Desktop-da müəllim MCP serveri (`teacher_mcp/README.md`) | «Siniflərimi göstər» real sinifləri qaytarır |

Nəticəni yazanda **ekranda nə gördüyünü** yaz, «işlədi» yox: ekran və baza ayrı
şeylərdir (bax CLAUDE.md, «təkrarlanan iştirakçı» dərsi).
