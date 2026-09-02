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

`/opt/masterai` VPS-də git repo checkout-udursa:

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
