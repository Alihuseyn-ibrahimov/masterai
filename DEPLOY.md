# MasterAI — VPS Deploy Təlimatı

Məqsəd: FastAPI backend-i (`pipeline/`+`server/`) VPS-də HTTPS ilə işə salmaq.
DilDostu/MasterNR1 ilə **eyni VPS/pattern** (`<SERVER_IP>`).

**VACİB — YALNIZ 1 worker:** `ConnectionManager` (WebSocket reyestri) və
`app.state.active_quiz_timeouts`/`active_material_tasks` proses-daxili
yaddaşdadır (Redis/xarici state yoxdur, bax `server/connection_manager.py`
modul qeydi). Birdən çox worker/proses WebSocket broadcast-ını və quiz
timeout-larını SÜKUTLA korlayar — heç vaxt `-w` dəyərini artırma.

## 0. Səndən lazım olanlar

| Nə | Qeyd |
|----|------|
| VPS SSH girişi | `root@<SERVER_IP>` (dildostu-live/masternr1-web ilə eyni server) |
| Subdomen | `masterai.prdostu.com` — DNS (Cloudflare) VPS IP-yə A qeydi |
| `GROQ_API_KEY` | console.groq.com/keys — digər layihələrdən AYRI açar tövsiyə olunur (limit paylaşılmasın) |
| `ANTHROPIC_API_KEY` (istəyə görə) | Groq uğursuz olanda fallback (`pipeline/providers.py`, `DEFAULT_ORDER = ["groq","claude","ollama"]`) |
| `JWT_SECRET` | **MƏCBURİ** — giriş tokenləri (≥32 simvol). Skript avtomatik yaradır (aşağı bax) |
| `ADMIN_API_KEY` | **MƏCBURİ** — `GET /admin/stats` + n8n "Gündəlik Statistika" workflow-u. Skript avtomatik yaradır |

## 1. Avtomatlaşdırılmış deploy (tövsiyə olunur)

```bash
git -C /opt/pr-agent/repo pull    # (repo artıq droplet-də checkout olunubsa)
GROQ_API_KEY=gsk_... bash /opt/pr-agent/repo/masterai/deploy/deploy_on_droplet.sh masterai.prdostu.com
```

`deploy/deploy_on_droplet.sh` altı addımı öz-özünə edir: venv+asılılıqlar,
`data/` qovluğu (8 sqlite fayl + `uploads/`), `.env` (JWT_SECRET/ADMIN_API_KEY
verilməyibsə avtomatik yaradılır), systemd servisi, nginx+WebSocket proxy,
certbot HTTPS. Sonunda ekrana çıxan `ADMIN_API_KEY`-i qeyd et — Addım 6-da
lazım olacaq.

Aşağıdakı bölmələr (2-5) həmin skriptin nə etdiyini addım-addım izah edir —
əl ilə/fərqli düzəndə etmək istəsən bax.

## 2. Kod deploy (VPS-də, əl ilə)

> **REAL VƏZİYYƏT (2026-09-10-da serverdən yoxlanılıb).** Aşağıdakı
> `/opt/masterai` yolu şablondur, canlı serverdə İSTİFADƏ OLUNMUR.
> `systemctl show masterai` nə deyir:
>
> ```
> WorkingDirectory=/opt/pr-agent/repo/masterai
> ExecStart=/opt/pr-agent/repo/masterai/.venv/bin/gunicorn ...
> ```
>
> Yəni kod `/opt/pr-agent/repo` checkout-unun içindədir. `/opt/masterai`
> qovluğu ÜMUMİYYƏTLƏ mövcud deyil. Bu uyğunsuzluq bir dəfə artıq vaxt
> itkisinə səbəb olub — sənədə baxıb yanlış yol verilib. Yolu buradan
> yox, HƏMİŞƏ `systemctl show masterai -p WorkingDirectory` ilə
> serverin özündən öyrən.

```bash
cd /opt/masterai            # (repo artıq /opt/masterai-dadırsa)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # sonra doldur (aşağı)
mkdir -p data/uploads
```

**Diqqət — kod strukturu:** `server/app.py` `pipeline/`-i **kök-səviyyəli**
idxal edir (`from pipeline.models import ...`) — `WorkingDirectory`
`masterai/`-in ÖZÜ olmalıdır (`masterai/server/` YOX), əks halda
`ModuleNotFoundError: pipeline`.

## 3. `.env` (prod)

Bax `.env.example` — tam dəyər siyahısı və DB yolları üçün. Qısaca:

```
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...        # istəyə görə
JWT_SECRET=...               # python -c "import secrets; print(secrets.token_urlsafe(48))"
ADMIN_API_KEY=...            # eyni üsulla
ADMIN_WEBHOOK_URL=https://<N8N_HOST>/webhook/<WEBHOOK_PATH>
USERS_DB_PATH=/opt/masterai/data/users.db
# ... (qalan 7 DB yolu + MATERIAL_UPLOAD_DIR, bax .env.example)
```

DB fayllarının `data/` alt-qovluğunda (kod qovluğundan AYRI) saxlanması
qəsdən seçim — gələcək kod yeniləmələri (əl ilə fayl köçürmə, bax bölmə
"Yeniləmə") DB-lərə TOXUNMAMALI.

## 4. systemd

```bash
sudo cp deploy/masterai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now masterai
curl -s localhost:8110/health      # {"status":"ok"}
```

## 5. nginx + HTTPS

```bash
# nginx-masterai.conf-da SEND_DOMAIN-i real domenlə (masterai.prdostu.com) əvəz et
sudo cp deploy/nginx-masterai.conf /etc/nginx/sites-available/masterai
sudo ln -sf /etc/nginx/sites-available/masterai /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d masterai.prdostu.com    # HTTPS sertifikatı
```

nginx konfiqurasiyasında **iki** `location` var: `/ws/` (WebSocket, uzun
timeout, `Upgrade`/`Connection` başlıqları) və `/` (adi HTTP, `20 MB`
material yükləmə limiti üçün `client_max_body_size 25M`).

## 6. Deploy-dan sonra: n8n "Gündəlik Statistika" workflow-unu aktivləşdir

Bu addım bilərəkdən Faza-4-də (n8n admin avtomatlaşdırması) edilməyib —
backend ictimai ünvana malik olmalı idi. İndi:

1. n8n-də `Ghlqz9ZHM3RXiRjS` ("MasterAI — Gündəlik Statistika") workflow-una gir
2. "Statistikanı Çək" (HTTP Request) node-unun URL-ini `https://masterai.prdostu.com/admin/stats` et
3. "MasterAI Admin Key" kredensialının dəyərini `.env`-dəki (və ya skript
   çıxışındakı) `ADMIN_API_KEY` ilə doldur
4. `test_workflow` ilə bir dəfə manual işə sal — Telegram-a real statistika gəlməlidir
5. Workflow-u `publish_workflow` ilə aktivləşdir (gündəlik saat 09:00 Bakı vaxtı işə düşəcək)

"Uğursuz Material Bildirişi" workflow-u (`9nwfkBe6BzrJu5Y8`) artıq aktivdir —
bu addım tələb etmir.

## Yoxlama (canlıda, mətnə güvənmə)

```bash
curl -s https://masterai.prdostu.com/health                              # {"status":"ok"}
curl -s -H "X-Admin-Key: <ADMIN_API_KEY>" https://masterai.prdostu.com/admin/stats
curl -s https://masterai.prdostu.com/admin/stats                         # {"detail":"Admin açarı səhvdir"} — 403 gözlənilir
```

Qeydiyyat+giriş+material yükləmə üçün real HTTP axını (`.planning/2026-09-02-masterai-material-upload/`-dakı smoke skriptlərinə bənzər) real domenlə təkrarlana bilər.

## Yeniləmə (növbəti dəfə)

Canlı serverdə checkout `/opt/pr-agent/repo`-dadır (yuxarıdakı qeydə bax):

```bash
cd /opt/pr-agent/repo && git pull
cd masterai && .venv/bin/pip install -r requirements.txt
sudo systemctl restart masterai
curl -s localhost:8110/health
```

DilDostu-nun DEPLOY.md-sindəki xəbərdarlığa bənzər risk: yeni endpoint/model
əlavə edəndən sonra restart unudulsa, app köhnə davranış göstərər.

## Bilinən məhdudiyyətlər (bu fazanın əhatəsində DEYİL)

- **Flutter app hələ yoxdur** — bu sandbox-da Flutter SDK yoxdur, ayrı fazadır
- **Backup/monitorinq** — `data/*.db` üçün avtomatik backup, disk dolması
  xəbərdarlığı və s. bu sənədin əhatəsində deyil
- **Ollama fallback VPS-də quraşdırılmayıb** — `DEFAULT_ORDER`-in üçüncü
  həlqəsi (`groq→claude→ollama`) yalnız `OLLAMA_HOST` əlçatan olanda işləyir;
  Groq+Claude adətən kifayətdir, əlavə quraşdırma tələb olunmur


---

# Veb sayt (2026-09-09-dan) — statik HTML

Flutter tətbiqi arxivləşdirildi, yerini statik veb sayt tutdu
(`masterai/web/`). Səbəb və müqayisə: `.planning/2026-09-09-masterai-app-redesign/`.

## Ünvan quruluşu

| Ünvan | Nə verir |
|---|---|
| `masterai.prdostu.com/` | Statik sayt (açılış səhifəsi + tətbiq səhifələri) |
| `masterai.prdostu.com/auth/...`, `/chats`, `/live/...` və s. | API (keçid dövrü üçün, nginx yol-kökünə görə ayırır) |
| `masterai.prdostu.com/ws/...` | WebSocket |
| `api.masterai.prdostu.com/` | Yalnız API (gələcək əsas ünvan) |

**Niyə API hər iki adda:** mövcud n8n workflow-u və köhnə client-lər kök
domenə müraciət edir. Kök domendəki API yolları KEÇİD tədbiridir.

**nginx-də kritik incəlik:** regex `location` prefiks `location`-dan
ÜSTÜNDÜR. `ws` API regex siyahısına salınsa `/ws/` bloku heç vaxt işə
düşməz və `Upgrade` başlıqları ötürülməz — WebSocket sükutla sınar.
`tests/test_nginx_routes.py` bunu qoruyur.

## İlk quraşdırma (bir dəfəlik)

```bash
# 1. DNS (Cloudflare): api.masterai → <SERVER_IP> (A qeydi)

# 2. Statik qovluq
ssh root@<SERVER_IP> "mkdir -p /opt/masterai-web"

# 3. nginx konfiqurasiyası
scp masterai/deploy/nginx-masterai.conf root@<SERVER_IP>:/etc/nginx/sites-available/masterai
ssh root@<SERVER_IP> "ln -sf /etc/nginx/sites-available/masterai /etc/nginx/sites-enabled/masterai && nginx -t"

# 4. Sertifikat (hər iki ad)
ssh root@<SERVER_IP> "certbot --nginx -d masterai.prdostu.com -d api.masterai.prdostu.com"

# 5. İlk fayl köçürməsi — AŞAĞIDAKI SKRİPTLƏ
```

## Hər dəfəki deploy

```powershell
cd masterai
powershell -ExecutionPolicy Bypass -File deploy\deploy_web.ps1
```

Skript `saas_core/deploy.ps1`-in **test qapısı** naxışını təkrarlayır:

1. `pytest` — keçməsə server TOXUNULMUR
2. `node --test` (Node varsa)
3. **`df` yoxlaması** — disk ≥98% olsa dayanır
4. `scp` ilə `web/` → `/opt/masterai-web/` (test qovluğu silinir)
5. `nginx -t` + `reload`
6. Canlı ünvandan healthcheck (sayt 200, API 200)

**Disk yoxlaması məcburidir:** bu VPS-də disk dolması əvvəllər
masterai-ni çökdürüb və `masternr1` (aktiv pilot) daxil dörd servisi
riskə atıb (bax `masterai/CLAUDE.md`, "Dərs: real deploy tələləri",
bənd 6).

## Build addımı yoxdur

npm, bundler, Flutter SDK — heç biri lazım deyil. Fayllar olduğu kimi
verilir. Bu, `saas_core` (mediapulse.az) ilə eyni yanaşmadır.

## Lokal yoxlama

`file://` ilə açmaq İŞLƏMİR — brauzer ES modullarını CORS səbəbi ilə
bloklayır (real Chromium testi ilə təsdiqləndi). Lokal server lazımdır:

```powershell
cd masterai\web
py -m http.server 8123
# brauzerdə: http://localhost:8123/
```


## Sual keyfiyyətinin yoxlanması

Canlı bazadakı sual dəstini insan yoxlaması üçün vərəqə çevirir. Yalnız
OXUYUR — servisə toxunmur, restart tələb etmir.

```bash
cd /opt/pr-agent/repo/masterai
.venv/bin/python -m pipeline.audit --list
.venv/bin/python -m pipeline.audit --set 3 --out /tmp/yoxlama.txt
```

Baza yolu defolt olaraq `WorkingDirectory`-yə nisbi (`question_sets.db`)
götürülür; başqa yerdədirsə `--db` ilə göstər.

**Alətin sərhədi:** cavabın faktiki olaraq doğru olduğunu deyə BİLMİR —
onu yalnız mənbə materialını oxuyan insan təsdiqləyə bilər. Alət yalnız
obyektiv şübhə əlamətlərini sayır və hansı sualdan başlamaq lazım
olduğunu göstərir. Bax `pipeline/quality.py` modul qeydi.
