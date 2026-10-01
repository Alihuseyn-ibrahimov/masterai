# Kurs lisenziyası deploy-u — Windows PowerShell-dən addım-addım

Bu, `RUNBOOK_kurs_lisenziyasi.md`-nin Windows üçün icra variantıdır. Səbəbli
fərq: əmrlər `ssh root@... '...'` şəklində DEYİL, açıq SSH sessiyasına
yapışdırılır. Windows PowerShell 5.1 `ssh`-a ötürülən mətndəki dırnaqları
pozur və sətir sonlarını CRLF edir; bash isə `\r`-dən sınır. Ona görə:

- **PowerShell** yalnız iki iş görür: SSH-i açmaq və saytı deploy etmək.
- **Server əmrləri** (`bash` blokları) açıq SSH pəncərəsinə yapışdırılır.

Hər blokdan sonra çıxışı oxu. «Gözlənilən» ilə uyğun gəlmirsə — DAYAN,
çıxışı mənə göndər. Ümumi vaxt: ~20 dəqiqə; sayt ~1-2 dəqiqə əlçatmaz olur
(3-cü və 4-cü addım arası). **Dərs olmayan saat seç.**

Lazım olanlar: tələbə sayı, sənin MasterAI hesabının e-poçtu.

---

## A. Kompüterdə kodu yenilə (PowerShell)

Repo qovluğunda (öz yolunu yaz):

```powershell
cd C:\YOL\quantum-pr-monitor
git fetch origin
git checkout claude/ai-engineering-monthly-project-g5cg2y
git pull
git log -1 --oneline
git status --short
```

Gözlənilən: son commit «Deploy addımları: PowerShell ...» (və ya daha yeni),
`git status` boş (və ya yalnız sənin öz faylların — `masterai/web/`-də
dəyişiklik OLMAMALIDIR).

Backend portunun kənardan bağlı olduğunu yoxla:

```powershell
Test-NetConnection <SERVER_IP> -Port 8110 | Select-Object TcpTestSucceeded
```

Gözlənilən: `False`. `True` görsən DAYAN (backend nginx-i yan keçərək açıqdır).

---

## B. Serverə qoşul (PowerShell)

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_rsa" root@<SERVER_IP>
```

Bundan sonrakı `bash` blokları **bu pəncərəyə** yapışdırılır. Pəncərəni
sona qədər BAĞLAMA — dəyişənlər (`$LIVE`, `$B`) sessiyada yaşayır.

---

## 0. Sessiya dəyişənləri (server)

```bash
LIVE=/opt/pr-agent/repo/masterai
BR=claude/ai-engineering-monthly-project-g5cg2y
STAMP=$(date +%Y%m%d-%H%M)
B=/root/masterai-backup/$STAMP
echo "LIVE=$LIVE  B=$B"
```

**Bağlantı qopsa:** yenidən qoşul, yuxarıdakı ilk iki sətri yapışdır, sonra
(3-cü addım artıq edilibsə) `STAMP` YENİ yaratma, mövcudu götür:

```sh
STAMP=$(ls -1 /root/masterai-backup | tail -1); B=/root/masterai-backup/$STAMP; echo $B
```

---

## 1. Ön yoxlama (server, heç nəyə toxunmur)

```bash
df -h / | tail -1
git -C /opt/pr-agent/repo branch --show-current
git -C /opt/pr-agent/repo status --short | head
systemctl cat masterai | grep -E "WorkingDirectory|ExecStart|-b "
readlink -f "$(systemctl show -p WorkingDirectory --value masterai)"
ls -l /etc/nginx/sites-enabled/ | grep masterai
```

Gözlənilən:
- disk 95%-dən az;
- branch `claude/ai-engineering-monthly-project-g5cg2y`, `status` boş;
- `-b 127.0.0.1:8110` (0.0.0.0 DEYİL);
- `readlink` sətri **dəqiq** `/opt/pr-agent/repo/masterai`. Başqa yol
  çıxsa DAYAN və mənə göndər — servis başqa qovluqdan işləyir;
- `masterai -> /etc/nginx/sites-available/masterai` (ox işarəsi = symlink).

---

## 2. Miqrasiya sınağı (server, servis işləməyə davam edir)

```bash
( set -e
  cd /opt/pr-agent/repo
  git fetch origin $BR
  mkdir -p /root/rehearsal-code-$STAMP
  git archive origin/$BR masterai | tar -x -C /root/rehearsal-code-$STAMP
  $LIVE/.venv/bin/python /root/rehearsal-code-$STAMP/masterai/deploy/migration_rehearsal.py \
      --from $LIVE --to /root/migration-rehearsal-$STAMP
)
```

Gözlənilən son sətir: **`HAMISI TƏMİZ - deploy edilə bilər`**.
`users: N -> N`, `chats: N -> N`, `question_sets: N -> N` rəqəmlərini YAZ.
`PROBLEM VAR` və ya xəta → DAYAN (servisə heç nə olmayıb).

---

## 3. Servisi dayandır + backup (server)

Bu blokdan sonra sayt API-si əlçatmazdır — 4-cü addıma DƏRHAL keç.

```bash
( set -e
  mkdir -p $B
  git -C /opt/pr-agent/repo rev-parse HEAD > $B/HEAD_before
  systemctl stop masterai
  cd $LIVE
  cp -a data $B/ 2>/dev/null || true
  cp -a *.db $B/ 2>/dev/null || true
  cp -a .env $B/
  cp -a "$(readlink -f /etc/nginx/sites-enabled/masterai)" $B/nginx-masterai.conf
  cp -a /opt/masterai-web $B/web
)
echo "backup: $B"; cat $B/HEAD_before
find $B -name "*.db" | sort; ls $B; du -sh $B
```

Gözlənilən: `.db` siyahısında `users.db`, `chats.db`, `question_sets.db`
var; `ls`-də `HEAD_before nginx-masterai.conf web` də görünür.
Xəta çıxsa: `systemctl start masterai` (köhnə versiya geri gəlir) və DAYAN.

---

## 4. Backend (server)

```bash
( set -e
  cd /opt/pr-agent/repo
  git checkout $BR
  git pull --ff-only
  git log -1 --format="%h %s"
)
systemctl start masterai; sleep 3
systemctl is-active masterai
curl -s http://127.0.0.1:8110/health; echo
curl -s -o /dev/null -w "/me/course -> %{http_code} (401 gözlənilir)\n" http://127.0.0.1:8110/me/course
```

Gözlənilən: commit A-dakı ilə eyni, `active`, `{"status":"ok"}`, `401`.
`git pull` xəta versə də servis yenə başlayır (köhnə kodla) — DAYAN, mənə göndər.
`failed` görsən: `journalctl -u masterai -n 80 --no-pager` → mənə göndər
(geri qaytarma: 12-ci addım).

---

## 5. Canlı bazanı yoxla (server)

```bash
cd $LIVE && .venv/bin/python deploy/migration_rehearsal.py --from $LIVE --to /root/migration-check-$STAMP
```

Gözlənilən: `HAMISI TƏMİZ` və rəqəmlər 2-ci addımdakı ilə EYNİ.

---

## 6. nginx — bir sətir (server)

```bash
CONF=$(readlink -f /etc/nginx/sites-enabled/masterai)
cd $LIVE && .venv/bin/python deploy/nginx_add_api_routes.py "$CONF"
grep -n "location ~ \^/(" "$CONF"
grep -c "managed by Certbot" "$CONF"
nginx -t && systemctl reload nginx && sleep 2 && echo "nginx yeniləndi"
```

Gözlənilən: `düzəldildi: ... |quiz|me|owner)(/|$) {`, Certbot sayı 0-dan
böyük, `test is successful`, `nginx yeniləndi`.

**Yalnız `nginx -t` uğursuz olsa** (köhnə faylı qaytarır):

```sh
cp -a $B/nginx-masterai.conf "$CONF" && nginx -t && systemctl reload nginx
```

---

## 7. Sayt (YENİ PowerShell pəncərəsi, kompüterdə)

SSH pəncərəsini bağlama. Yeni PowerShell aç:

```powershell
cd C:\YOL\quantum-pr-monitor\masterai
powershell -ExecutionPolicy Bypass -File deploy\deploy_web.ps1
```

Gözlənilən: veb testləri keçir, disk faizi, köçürmə, sonda healthcheck uğurlu.
Testlər uğursuzdursa skript serverə TOXUNMUR — çıxışı mənə göndər.

---

## 8. Mənbədən yoxlama (SSH pəncərəsi)

```bash
cd $LIVE && .venv/bin/python deploy/diagnostics/attack_check.py public \
    --base https://masterai.prdostu.com --api https://api.masterai.prdostu.com \
    --direct http://<SERVER_IP>:8110
curl -s https://masterai.prdostu.com/index.html | grep -o "v=20260930a" | head -1
curl -s -o /dev/null -w "bagli.html -> %{http_code} (200)\n" https://masterai.prdostu.com/bagli.html
curl -s -o /dev/null -w "sahib.html -> %{http_code} (200)\n" https://masterai.prdostu.com/sahib.html
```

Gözlənilən: hücum yoxlaması **`23 keçdi, 0 uğursuz` / `HAMISI TƏMİZ`**,
sonra `v=20260930a`, `200`, `200`. Hücum yoxlamasını təkrar işlətsən,
arada 1 dəqiqə gözlə (qeydiyyat limiti).

Brauzerdə öz hesabınla daxil ol: çatlar açılır, sarı banner YOXDUR.

---

## 9. Platforma sahibi (SSH pəncərəsi)

`SƏNİN@EPOÇTUN` yerinə MasterAI-da daxil olduğun e-poçtu yaz:

```bash
cd $LIVE && .venv/bin/python deploy/set_platform_owner.py --from $LIVE --email SƏNİN@EPOÇTUN
```

Gözlənilən: `is_platform_owner = 1`. Sonra saytda **Çıxış → yenidən Giriş** →
Profil → «Sahib paneli» → siyahıda «MasterAI» (müddətsiz).

---

## 10. İngilis kursu (brauzer, Sahib paneli)

1. Yeni kurs: ad, profil **ingilis dili**, sınaq **30 gün**, yer = tələbə sayı.
2. **Müəllim dəvəti** → linki kopyala, müəllimə göndər (7 gün, birdəfəlik).
3. Qeydiyyat kodunu tələbələrə **baseline bitənə qədər VERMƏ**.

---

## 11. Telegram (n8n)

«MasterAI — Gündəlik Statistika» workflow-unu əl ilə bir dəfə işlət →
Telegram-a mesaj gəlməlidir, execution `success`. «Bitmək üzrə» bölməsi
boşdur — kurs 30 gündür, normaldır.

---

## 12. Geri qaytarma — YALNIZ nəsə sınarsa (SSH pəncərəsi)

Kodu köhnə versiyaya qaytar:

```sh
cd /opt/pr-agent/repo && git checkout $(cat $B/HEAD_before)
systemctl restart masterai; sleep 3; systemctl is-active masterai
```

nginx və sayt da köhnəyə:

```sh
cp -a $B/nginx-masterai.conf "$(readlink -f /etc/nginx/sites-enabled/masterai)" && nginx -t && systemctl reload nginx
rm -rf /opt/masterai-web && cp -a $B/web /opt/masterai-web
```

⚠️ Köhnə kodda qeydiyyat AÇIQ, kurs sərhədi YOXDUR — geri qaytarılmış
vəziyyətdə uzun qalma. Yenidən irəli getmək üçün 4-cü addımı təkrarla
(geri qaytarma müddətində yaranan qeydlər avtomatik kurs #1-ə düşür).

---

## Bitdi

SSH-dən çıx: `exit`. Mənə göndər: 2, 5, 8-ci addımların çıxışı və 9-cu
addımın nəticəsi — `progress.md`-yə faktla yazım.
