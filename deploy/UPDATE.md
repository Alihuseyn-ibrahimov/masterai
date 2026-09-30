# MasterAI — canlı serverin YENİLƏNMƏSİ

Bu, mövcud serverə yeni versiya çıxarmaq üçündür. İlk quraşdırma ayrıdır
(`deploy_on_droplet.sh` — və o skript **yeniləmə üçün işlədilməməlidir**,
səbəbi öz başlığında yazılıb).

**Server:** `root@<SERVER_IP>` · `masterai.prdostu.com`
**Backend:** `/opt/pr-agent/repo/masterai` (systemd: `masterai`)
**Sayt:** `/opt/masterai-web` (nginx)

---

## 0. Nə vaxt

**Sinif dərsi olmayan vaxt.** Restart canlı bazada `ALTER TABLE`
işlədir və gedən sessiyanı kəsir.

Backend və sayt **EYNİ GÜN, ardıcıl** getməlidir. Yarımçıq vəziyyətdə
(köhnə sayt + yeni backend, və ya əksi) sessiya ümumiyyətlə açılmır.

---

## 1. Ön yoxlama (serverə toxunmadan)

```bash
ssh root@<SERVER_IP> 'df -h / && free -m | head -2'
```

- **Disk 95%-dən çoxdursa DAYAN.** Bu maşında disk dolması əvvəl
  `masterai`-ni çökdürüb və masternr1 (aktiv pilot) daxil beş servisi
  riskə atıb. Təmizləmə: `rm -rf /root/.cache/selenium`,
  `journalctl --vacuum-size=100M`.

```bash
ssh root@<SERVER_IP> 'cd /opt/pr-agent/repo && git branch --show-current'
```

- **`main` çıxarsa dayan** — iş `claude/ai-engineering-monthly-project-g5cg2y`
  branch-ındadır. `git pull` sükutla `main`-i yeniləyər və `masterai/`
  dəyişməz qalar.

---

## 2. BACKUP (atlanması qadağandır)

⚠️ **Bazaların bir hissəsi `data/`-da DEYİL.** `.env`-də yalnız bir
neçə yol təyin olunub; qalanları `WorkingDirectory`-də (repo
checkout-unda) yaranır. Yalnız `data/`-nı götürən backup **canlı
sessiyaları, sual banklarını, ev tapşırıqlarını və nişanları İTİRƏR**.

```bash
ssh root@<SERVER_IP> '
  cd /opt/pr-agent/repo/masterai
  STAMP=$(date +%Y%m%d-%H%M)
  mkdir -p /root/masterai-backup/$STAMP
  cp -a data /root/masterai-backup/$STAMP/ 2>/dev/null || true
  cp -a *.db /root/masterai-backup/$STAMP/ 2>/dev/null || true
  cp -a .env /root/masterai-backup/$STAMP/
  echo "--- backup içindəkilər ---"
  find /root/masterai-backup/$STAMP -name "*.db" | sort
  du -sh /root/masterai-backup/$STAMP
'
```

**Çıxışda bu bazaları GÖRMƏLİSƏN** (yoxdursa hələ yaradılmayıb, normaldır):
`users`, `chats`, `messages`, `materials`, `questions`, `quiz_sessions`,
`quiz_attempts`, `friendships`, `question_sets`, `live_sessions`,
`homework`, `badges`.

---

## 3. Backend

```bash
ssh root@<SERVER_IP> '
  cd /opt/pr-agent/repo
  git checkout claude/ai-engineering-monthly-project-g5cg2y
  git pull
  cd masterai
  .venv/bin/pip install -q -r requirements.txt
  systemctl restart masterai
  sleep 3
  systemctl is-active masterai
  curl -s http://127.0.0.1:8110/health
'
```

`active` və `{"status":"ok"}` görünməlidir. Görünməsə:
`journalctl -u masterai -n 50 --no-pager`.

---

## 4. Sayt

Windows-dan (`masterai/` qovluğunda):

```powershell
powershell -ExecutionPolicy Bypass -File deploy\deploy_web.ps1
```

Skript özü test qapısından keçirir, disk yoxlayır, atomik əvəzləmə edir,
icazələri düzəldir (`a+rX` — olmasa nginx 403 verir) və canlı ünvandan
healthcheck edir.

nginx konfiqurasiyası dəyişibsə:

⚠️ **Repo faylını canlının üstünə `scp` ilə YAZMA.** Canlı fayla certbot
HTTPS sətirlərini (`listen 443 ssl`, sertifikat yolları, http->https
yönləndirmə) özü əlavə edib; `deploy/nginx-masterai.conf`-da onlar YOXDUR.
Üstünə yazmaq saytı HTTPS-siz qoyar. Yalnız dəyişən sətri düzəlt, əvvəl
backup al, `nginx -t` keçməsə backup-ı qaytar. Nümunə:
`deploy/nginx_add_api_routes.py` və `deploy/RUNBOOK_kurs_lisenziyasi.md` §6.

---

## 5. MƏNBƏDƏN yoxlama (mətnə görə yox)

Bu addım atlanmamalıdır — «sayt açıldı» heç nə isbat etmir.

Gözlənilən dəyərlər lokal serverdə ÖLÇÜLÜB (güman deyil).

```bash
# --- SAYT deploy olundumu? ---
# 5.1 Köhnə PIN səhifəsi getdi
curl -s -o /dev/null -w "qosul.html      → %{http_code}  (404 gözlənilir)\n" \
  https://masterai.prdostu.com/qosul.html

# 5.2 Yeni səhifə gəldi
curl -s -o /dev/null -w "sessiya.html    → %{http_code}  (200 gözlənilir)\n" \
  https://masterai.prdostu.com/sessiya.html

# --- BACKEND deploy olundumu? ---
# 5.3 Yeni endpoint VAR. 401 = marşrut mövcuddur, sadəcə token yoxdur.
#     404 gəlsə backend KÖHNƏDİR (git pull/restart tam getməyib).
curl -s -o /dev/null -w "join-requests   → %{http_code}  (401 gözlənilir)\n" \
  -X POST https://masterai.prdostu.com/chats/join-requests \
  -H 'Content-Type: application/json' -d '{"code":"ZZZZZZ"}'

# 5.4 Köhnə boşluq HƏQİQƏTƏN bağlandı. Bu, ən vacib yoxlamadır:
#     404 = marşrut silinib. 200/401 gəlsə KÖHNƏ BACKEND İŞLƏYİR və
#     çat ID-si ilə sərbəst qoşulma hələ mümkündür.
curl -s -o /dev/null -w "köhnə join yolu → %{http_code}  (404 gözlənilir)\n" \
  -X POST https://masterai.prdostu.com/chats/1/join

# 5.5 JS keşlənmir (köhnə JS yeni backend-lə toqquşardı)
curl -sI https://masterai.prdostu.com/assets/js/live.js | grep -i cache-control
```

**Miqrasiyanın həqiqətən işlədiyini bazadan yoxla:**

`sqlite3` CLI serverdə olmaya bilər — venv-in Python-u həmişə var:

```bash
ssh root@<SERVER_IP> '
cd /opt/pr-agent/repo/masterai
.venv/bin/python - <<PY
import os, sqlite3
path = os.environ.get("CHATS_DB_PATH", "chats.db")
if not os.path.exists(path):
    for line in open(".env"):
        if line.startswith("CHATS_DB_PATH="):
            path = line.split("=", 1)[1].strip()
print("baza:", path)
c = sqlite3.connect(path)
cols = [r[1] for r in c.execute("PRAGMA table_info(chats)")]
print("invite_code sütunu:", "VAR" if "invite_code" in cols else "YOXDUR ‼")
kodsuz = c.execute(
    "SELECT COUNT(*) FROM chats WHERE kind=? AND (invite_code IS NULL OR invite_code=?)",
    ("group", "")).fetchone()[0]
print("kodsuz qrup çatı:", kodsuz, "(0 olmalıdır)")
print("üzvlük sayı:", c.execute("SELECT COUNT(*) FROM chat_members").fetchone()[0],
      "(backup-dakı ilə eyni olmalıdır)")
PY
'
```

**Miqrasiya bu sandbox-da real köhnə sxem üzərində sınanıb** (2026-09-12):
qrup çatı kod aldı, şəxsi çat almadı, bütün üzvlüklər qaldı, köhnə
bitmiş sessiya (PIN + hesabat daxil) oxundu, anonim iştirakçı sətri
qorundu, tələbə tarixçəsi işlədi. Yəni gözlənilən nəticə bilinir.

**Uc-uca son təsdiq (ən vacibi):** öz müəllim hesabınla saytda bir
qrup çatı aç, dəvət kodunu ikinci hesabla yaz, təsdiqlə, çatdan sessiya
başlat, qoşul, bir sual cavabla, lövhəyə bax.

---

## 6. Geri qaytarma (nəsə sınarsa)

```bash
ssh root@<SERVER_IP> '
  systemctl stop masterai
  cd /opt/pr-agent/repo/masterai
  STAMP=<backup qovluğunun adı>
  cp -a /root/masterai-backup/$STAMP/data/. data/ 2>/dev/null || true
  cp -a /root/masterai-backup/$STAMP/*.db . 2>/dev/null || true
  cd /opt/pr-agent/repo && git checkout <əvvəlki commit>
  systemctl start masterai
'
```

**Diqqət:** `ALTER TABLE` ilə əlavə olunmuş sütunlar köhnə kodu
SINDIRMIR (əlavə sütun oxunmur), yəni yalnız kodu geri qaytarmaq adətən
kifayətdir. Baza bərpası isə həmin müddətdə yaranmış YENİ datanı silir —
ona görə əvvəlcə yalnız kodu geri qaytarmağı sına.

---

## 7. Deploy-dan sonra

`.planning/2026-09-11-masterai-class-chat/progress.md`-ə nəticəni yaz:
nə işlədi, nə işləmədi, jurnalda nə göründü. Rəqəmi və faktı yaz,
«yəqin işləyir» yazma.
