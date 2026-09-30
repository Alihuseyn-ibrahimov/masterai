# Deploy runbook — kurs lisenziyası (Faza 9)

Bu, `deploy/UPDATE.md`-nin bu buraxılış üçün DƏQİQLƏŞDİRİLMİŞ variantıdır.
Fərqlər: miqrasiya əvvəlcə SURƏTDƏ sınanır, backup servis DAYANMIŞ halda
alınır, nginx faylı üstünə yazılmır (cərrahi düzəliş), deploy-dan sonra
hücum yoxlaması işlədilir.

**Server:** `root@<SERVER_IP>` · **Branch:** `claude/ai-engineering-monthly-project-g5cg2y`

Hər addımdan sonra çıxışı oxu. Gözlənilən nəticə görünmürsə — DAYAN,
növbəti addıma keçmə.

---

## 0. Başlamazdan əvvəl

**Vaxt:** dərs olmayan saat. Eyni VPS-də masternr1 (aktiv pilot) işləyir —
disk/restart ona da təsir edir.

**Lazım olanlar:**

| Nə | Kimdən | Nə üçün |
|---|---|---|
| Tələbə sayı | kurs | kursun yer limiti (`seat_limit`) |
| Sənin MasterAI hesabının e-poçtu | sən | platforma sahibi bayrağı |
| Müəllimin e-poçtu | kurs | dəvət linkini göndərmək |

**Baseline:** kursun qeydiyyat kodunu tələbələrə baseline ölçüsü (5-7 gün,
sistem İŞLƏDİLMƏDƏN) bitənə qədər VERMƏ. Deploy etmək olar — kod
verilməyincə tələbə qeydiyyatdan keçə bilməz. Nəyin ölçüləcəyini kursla
razılaşdır (məs. müəllimin bir test hazırlamağa sərf etdiyi dəqiqə,
həftəlik ev tapşırığını təhvil verənlərin faizi).

---

## 1. Ön yoxlama (heç nəyə toxunmur)

```bash
ssh root@<SERVER_IP> '
  df -h / | tail -1
  cd /opt/pr-agent/repo && git branch --show-current && git status --short | head
  systemctl cat masterai | grep -E "WorkingDirectory|EnvironmentFile|ExecStart|-b "
  ls -l /etc/nginx/sites-enabled/ | grep masterai
'
```

Gözlənilən:
- disk 95%-dən az (çoxdursa `deploy/VPS_MAINTENANCE.md`);
- branch `claude/ai-engineering-monthly-project-g5cg2y`, `git status` boş;
- `WorkingDirectory` — **aşağıdakı bütün addımlarda `LIVE` budur**
  (repo unit faylında `/opt/masterai` yazılıb, `UPDATE.md`-də
  `/opt/pr-agent/repo/masterai` — HANSI olduğunu buradan götür);
- bind `127.0.0.1:8110` (`0.0.0.0` görsən DAYAN: nginx yan keçilə bilər);
- `sites-enabled/masterai` **symlink** (`->`) olmalıdır.

---

## 2. Miqrasiya SINAĞI — canlı bazanın surətində (servis işləyir)

`git fetch` yalnız uzaq ref-i yeniləyir, iş qovluğuna toxunmur. Yeni kod
ayrıca qovluğa açılır, canlı venv ilə işlədilir (paketlər dəyişməyib).

```bash
ssh root@<SERVER_IP> '
  set -e
  LIVE=/opt/pr-agent/repo/masterai          # 1-ci addımdakı WorkingDirectory
  STAMP=$(date +%Y%m%d-%H%M)
  cd /opt/pr-agent/repo
  git fetch origin claude/ai-engineering-monthly-project-g5cg2y
  mkdir -p /root/rehearsal-code-$STAMP
  git archive origin/claude/ai-engineering-monthly-project-g5cg2y masterai | tar -x -C /root/rehearsal-code-$STAMP
  $LIVE/.venv/bin/python /root/rehearsal-code-$STAMP/masterai/deploy/migration_rehearsal.py \
      --from $LIVE --to /root/migration-rehearsal-$STAMP
'
```

Son sətir **`HAMISI TƏMİZ - deploy edilə bilər`** olmalıdır. `users: N -> N`,
`chats: N -> N`, `question_sets: N -> N` rəqəmlərini YAZ — 5-ci addımda
müqayisə olunacaq. `PROBLEM VAR` görsən DAYAN və çıxışı mənə göndər.

Skript canlı bazanı yalnız-oxuma rejimində açır; sınaq surətdə gedir.
Sınaqdan sonra surət qovluğunu silmək olar.

---

## 3. Servisi dayandır, BACKUP (atlanması qadağandır)

Servis dayanmış halda `cp` ardıcıl surət verir (işləyən SQLite-dan
kopyalamaq yarımçıq yazını tuta bilər).

```bash
ssh root@<SERVER_IP> '
  set -e
  LIVE=/opt/pr-agent/repo/masterai
  STAMP=$(date +%Y%m%d-%H%M)
  B=/root/masterai-backup/$STAMP
  mkdir -p $B
  git -C /opt/pr-agent/repo rev-parse HEAD > $B/HEAD_before
  systemctl stop masterai
  cd $LIVE
  cp -a data $B/ 2>/dev/null || true
  cp -a *.db $B/ 2>/dev/null || true
  cp -a .env $B/
  cp -a "$(readlink -f /etc/nginx/sites-enabled/masterai)" $B/nginx-masterai.conf
  cp -a /opt/masterai-web $B/web
  echo "backup: $B"; cat $B/HEAD_before
  find $B -name "*.db" | sort; du -sh $B
'
```

`backup:` yolunu YAZ (geri qaytarmada lazımdır). `.db` siyahısında
`users.db`, `chats.db`, `question_sets.db` mütləq olmalıdır.

**Servis indi dayanıqdır** — 4-cü addıma dərhal keç.

---

## 4. Backend

```bash
ssh root@<SERVER_IP> '
  set -e
  cd /opt/pr-agent/repo
  git checkout claude/ai-engineering-monthly-project-g5cg2y
  git pull --ff-only
  git log -1 --format="%h %s"
  systemctl start masterai
  sleep 3
  systemctl is-active masterai
  curl -s http://127.0.0.1:8110/health; echo
  curl -s -o /dev/null -w "/me/course (lokal) -> %{http_code} (401 gözlənilir)\n" http://127.0.0.1:8110/me/course
'
```

`active`, `{"status":"ok"}` və `401`. Olmasa:
`journalctl -u masterai -n 80 --no-pager` → 9-cu addım (geri qaytarma).

---

## 5. Miqrasiyanı CANLI bazada yoxla (mənbədən)

Eyni skript, bu dəfə artıq miqrasiya olunmuş canlı bazanın surəti üzərində:

```bash
ssh root@<SERVER_IP> '
  LIVE=/opt/pr-agent/repo/masterai
  cd $LIVE && .venv/bin/python deploy/migration_rehearsal.py \
      --from $LIVE --to /root/migration-check-$(date +%Y%m%d-%H%M)
'
```

`HAMISI TƏMİZ` VƏ `users/chats/question_sets` rəqəmləri 2-ci addımdakı
ilə **eyni** olmalıdır (arada yeni qeydiyyat olmayıbsa).

---

## 6. nginx — CƏRRAHİ düzəliş (üstünə YAZMA)

⚠️ `scp deploy/nginx-masterai.conf ...` **İŞLƏTMƏ**: canlı faylda certbot-un
yazdığı HTTPS sətirləri var, repo faylında yoxdur — sayt HTTPS-siz qalar.
Dəyişən yeganə şey: kök domendə API siyahısına `me` və `owner`.

```bash
ssh root@<SERVER_IP> '
  CONF=$(readlink -f /etc/nginx/sites-enabled/masterai)
  cd /opt/pr-agent/repo/masterai
  .venv/bin/python deploy/nginx_add_api_routes.py "$CONF" || exit 1
  grep -n "location ~ \^/(" "$CONF"
  grep -c "managed by Certbot" "$CONF"
  if nginx -t; then systemctl reload nginx && echo "nginx yeniləndi"; \
  else echo "nginx -t UĞURSUZ - geri qaytarılır"; \
       cp -a /root/masterai-backup/<STAMP>/nginx-masterai.conf "$CONF" && nginx -t; fi
'
```

`<STAMP>` — 3-cü addımdakı backup adı. Gözlənilən: `düzəldildi: location ~
^/(...|quiz|me|owner)(/|$) {`, Certbot sayı 0-dan böyük, `nginx yeniləndi`.

---

## 7. Sayt

Windows-dan (`masterai/` qovluğunda):

```powershell
powershell -ExecutionPolicy Bypass -File deploy\deploy_web.ps1
```

Skript köhnə saytı silir — ona görə 3-cü addımda `web/` backup-a alındı.

---

## 8. MƏNBƏDƏN yoxlama

### 8.1 Hücum yoxlaması (VPS-dən, anonim, heç nə yaratmır)

```bash
ssh root@<SERVER_IP> '
  cd /opt/pr-agent/repo/masterai
  .venv/bin/python deploy/diagnostics/attack_check.py public \
      --base https://masterai.prdostu.com --api https://api.masterai.prdostu.com \
      --direct http://<SERVER_IP>:8110
'
```

Son sətir **`HAMISI TƏMİZ`** (lokalda repo nginx konfiqurasiyası arxasında
22/22 keçib; `--direct` bəndi ayrıca sınanıb: açıq port → XƏTA, bağlı → OK).
Skript əvvəlcə `/me/course -> 401` yoxlayır; keçməsə DAYANIR (köhnə
versiyada qeydiyyat açıqdır və sınaq real hesab yaradardı).

Parol sınağı bəndi `hucum-yoxlama@masterai-yoxlama.az` ünvanını VPS-in
IP-si üçün 15 dəqiqəlik bloklayır — belə hesab yoxdur, heç kimə təsir etmir.

### 8.2 Sayt yeni versiyadırmı

```bash
curl -s https://masterai.prdostu.com/index.html | grep -o "v=20260930a" | head -1
curl -s -o /dev/null -w "bagli.html -> %{http_code} (200)\n" https://masterai.prdostu.com/bagli.html
curl -s -o /dev/null -w "sahib.html -> %{http_code} (200)\n" https://masterai.prdostu.com/sahib.html
curl -sI https://masterai.prdostu.com/ | head -1
```

### 8.3 Mövcud istifadəçilər bağlanmayıb

Öz hesabınla daxil ol → çatlar açılır, banner YOXDUR (kurs #1 müddətsizdir).
Bir tələbə hesabı ilə də yoxla.

---

## 9. Platforma sahibi

```bash
ssh root@<SERVER_IP> '
  cd /opt/pr-agent/repo/masterai
  .venv/bin/python deploy/set_platform_owner.py --from $PWD --email <SƏNİN_EPOÇTUN>
'
```

Gözlənilən: `is_platform_owner = 1`. Sonra saytda **çıx və yenidən daxil
ol** → Profil səhifəsində «Sahib paneli» linki → `sahib.html`-də kurs #1
«MasterAI» (müddətsiz) görünür.

---

## 10. İngilis dili kursu

Sahib panelində:
1. **Yeni kurs:** ad, profil «ingilis dili», sınaq 30 gün, yer = tələbə sayı.
2. **Müəllim dəvəti** → linki müəllimə göndər (7 gün etibarlıdır, birdəfəlikdir).
3. **Qeydiyyat kodu:** baseline bitənə qədər tələbələrə VERMƏ (bax 0).

Müəllim qeydiyyatdan keçəndən sonra: panel → kursun müəllim sayı 1.

---

## 11. Telegram xəbərdarlığı (real)

n8n → «MasterAI — Gündəlik Statistika» → əl ilə bir dəfə işlət. Telegram-a
mesaj GƏLMƏLİDİR (sınaq kursu 30 gündür, «bitmək üzrə» bölməsi boş olacaq —
bu normaldır). n8n-də execution statusu `success` olmalıdır.

---

## 12. Geri qaytarma

**Əvvəlcə yalnız kodu** qaytar (yeni sütunlar köhnə kodu sındırmır):

```bash
ssh root@<SERVER_IP> '
  B=/root/masterai-backup/<STAMP>
  cd /opt/pr-agent/repo && git checkout $(cat $B/HEAD_before)
  systemctl restart masterai && sleep 3 && systemctl is-active masterai
'
```

⚠️ Köhnə kodda qeydiyyat AÇIQDIR — geri qaytarma qapalı qeydiyyatı da
aradan qaldırır. Qeydiyyat kodunu heç kimə verməmisənsə risk kiçikdir.

nginx: `cp $B/nginx-masterai.conf "$(readlink -f /etc/nginx/sites-enabled/masterai)" && nginx -t && systemctl reload nginx`
(köhnə nginx faylı yeni backend ilə də işləyir — sadəcə `/me`, `/owner` kök domendə açılmır).

Sayt: `rm -rf /opt/masterai-web && cp -a $B/web /opt/masterai-web`.

**Baza bərpası** yalnız data korlanıbsa (`systemctl stop masterai`,
`cp -a $B/data/. $LIVE/data/`, `cp -a $B/*.db $LIVE/`, start) — deploy-dan
sonra yaranmış YENİ data itir.

---

## 13. Sonra

`.planning/2026-09-29-masterai-course-licensing/progress.md`-ə yaz: hər
addımın çıxışı (rəqəmlər), nə gözlənildiyi kimi getmədi. «Yəqin işləyir» yazma.
