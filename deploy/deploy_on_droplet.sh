#!/usr/bin/env bash
# MasterAI — DigitalOcean droplet-də deploy skripti.
# Bu skript YERLƏŞDİYİ repo checkout-unu işlədir (klon etmir) — dildostu-nun
# eyni naxışı (bax dildostu/server/deploy/deploy_on_droplet.sh).
#
# İşlətmə (droplet-də, root):
#   1) Mövcud checkout-u yenilə:   git -C /opt/pr-agent/repo pull
#   2) Skripti işə sal:
#      GROQ_API_KEY=gsk_... bash /opt/pr-agent/repo/masterai/deploy/deploy_on_droplet.sh masterai.prdostu.com
#
# VACİB: MasterAI YALNIZ 1 worker ilə işləməlidir (bax masterai.service
# qeydi — WebSocket reyestri və quiz timeout-ları proses-daxili yaddaşda).
set -euo pipefail

DOMAIN="${1:-masterai.prdostu.com}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV="$(dirname "$SCRIPT_DIR")"

if [ -z "${GROQ_API_KEY:-}" ]; then
  echo "XETA: GROQ_API_KEY environment deyiskeni verilmelidir." >&2
  exit 1
fi
echo "Server qovlugu: $SRV"

echo "=== 1/7 sistem paketleri ==="
# pytesseract (OCR) ve selenium (JS-rendering) Python bagli paketleridir,
# ozleri deyil — real VPS-de tesseract-ocr olmadigi ucun sekil materiali
# "tesseract is not installed" xetasi ile ugursuz oldu (bax masterai/
# CLAUDE.md, "Derse: real deploy zamani rast gelinen telelar", bend 5).
apt-get update -qq
apt-get install -y -qq tesseract-ocr

echo "=== 2/7 venv + asililiqlar ==="
cd "$SRV"
python3 -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt

echo "=== 3/7 data qovlugu ==="
mkdir -p "$SRV/data/uploads"

echo "=== 4/7 .env ==="
JWT_SECRET_VAL="${JWT_SECRET:-$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')}"
ADMIN_API_KEY_VAL="${ADMIN_API_KEY:-$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')}"
{
  echo "GROQ_API_KEY=$GROQ_API_KEY"
  [ -n "${ANTHROPIC_API_KEY:-}" ] && echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY"
  echo "JWT_SECRET=$JWT_SECRET_VAL"
  echo "ADMIN_API_KEY=$ADMIN_API_KEY_VAL"
  echo "ADMIN_WEBHOOK_URL=${ADMIN_WEBHOOK_URL:-https://<N8N_HOST>/webhook/<WEBHOOK_PATH>}"
  echo "USERS_DB_PATH=$SRV/data/users.db"
  echo "CHATS_DB_PATH=$SRV/data/chats.db"
  echo "MESSAGES_DB_PATH=$SRV/data/messages.db"
  echo "MATERIALS_DB_PATH=$SRV/data/materials.db"
  echo "QUESTIONS_DB_PATH=$SRV/data/questions.db"
  echo "QUIZ_SESSIONS_DB_PATH=$SRV/data/quiz_sessions.db"
  echo "QUIZ_ATTEMPTS_DB_PATH=$SRV/data/quiz_attempts.db"
  echo "FRIENDSHIPS_DB_PATH=$SRV/data/friendships.db"
  echo "MATERIAL_UPLOAD_DIR=$SRV/data/uploads"
} > "$SRV/.env"
chmod 600 "$SRV/.env"
echo "ADMIN_API_KEY (n8n 'Gündəlik Statistika' workflow-una lazım olacaq): $ADMIN_API_KEY_VAL"

echo "=== 5/7 systemd servis ==="
cat > /etc/systemd/system/masterai.service <<UNIT
[Unit]
Description=MasterAI FastAPI backend
After=network.target

[Service]
Type=simple
WorkingDirectory=$SRV
EnvironmentFile=$SRV/.env
ExecStart=$SRV/.venv/bin/gunicorn server.app:app -k uvicorn.workers.UvicornWorker -w 1 -b 127.0.0.1:8110
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now masterai
sleep 2
echo "--- health (localhost) ---"
curl -s http://127.0.0.1:8110/health || echo "(health cavab vermedi — jurnal: journalctl -u masterai -n 30)"
echo

echo "=== 6/7 nginx reverse proxy ($DOMAIN) ==="
cat > /etc/nginx/sites-available/masterai <<NGINX
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    server_name $DOMAIN;

    location /ws/ {
        proxy_pass http://127.0.0.1:8110;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 3600s;
    }

    location / {
        proxy_pass http://127.0.0.1:8110;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 30s;
        client_max_body_size 25M;
    }

    listen 80;
}
NGINX
ln -sf /etc/nginx/sites-available/masterai /etc/nginx/sites-enabled/masterai
nginx -t && systemctl reload nginx

echo "=== 7/7 HTTPS (certbot) ==="
if ! command -v certbot >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq certbot python3-certbot-nginx
fi
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect || \
  echo "(certbot ugursuz — DNS yayilmayibsa sonra: certbot --nginx -d $DOMAIN)"

echo
echo "=== BITDI ==="
echo "Yoxla:  curl https://$DOMAIN/health"
echo "Yenilemek:  git -C /opt/pr-agent/repo pull && systemctl restart masterai"
echo
echo "QALAN ƏL İŞİ:"
echo "1) DNS: Cloudflare-də $DOMAIN -> bu droplet-in IP-si (A qeydi)"
echo "2) n8n 'Gündəlik Statistika' workflow-unu aktivləşdir: 'Statistikanı Çək'"
echo "   node-unun URL-ini https://$DOMAIN/admin/stats et, 'MasterAI Admin Key'"
echo "   kredensialının dəyərini yuxarıdakı ADMIN_API_KEY ilə doldur, publish et."
