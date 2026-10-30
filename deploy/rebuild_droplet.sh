#!/usr/bin/env bash
# MasterAI — TƏMİZ droplet-də sıfırdan qurulma (2026-10-30).
#
# Niyə: DigitalOcean hesabı ödənişə görə dayandırıldı və droplet silindi.
# Köhnə qurulma `/opt/pr-agent/repo` monorepo checkout-undan işləyirdi,
# sayt əl ilə `scp` ilə gəlirdi, sistem paketləri (Chrome, tesseract,
# swap, ufw 80) ayrı-ayrı hadisələrdən sonra əl ilə əlavə olunmuşdu.
# Bu skript HAMISINI bir yerə yığır və kodu birbaşa bu repodan götürür.
#
# `deploy_on_droplet.sh`-dan fərqi:
#   - repo-nu ÖZÜ klonlayır (`/opt/masterai`), monorepo lazım deyil;
#   - statik saytı da qoyur (`/opt/masterai-web`) və REAL nginx faylını
#     (`deploy/nginx-masterai.conf`) işlədir — sayt + API + WebSocket;
#   - `.env` VARSA ona TOXUNMUR (JWT_SECRET dəyişsə hamı sistemdən çıxar);
#   - təkrar işlədilə bilər: ikinci icra kodu yeniləyir, datanı saxlayır.
#
# İşlətmə (Ubuntu 24.04, root):
#   curl -fsSL https://raw.githubusercontent.com/Alihuseyn-ibrahimov/masterai/main/deploy/rebuild_droplet.sh -o rebuild.sh
#   GROQ_API_KEY=gsk_... ANTHROPIC_API_KEY=sk-ant-... bash rebuild.sh
#
# Könüllü mühit dəyişənləri: ANTHROPIC_API_KEY, ADMIN_WEBHOOK_URL,
# JWT_SECRET, ADMIN_API_KEY, BRANCH (defolt main), SKIP_CERTBOT=1.
set -euo pipefail

REPO_URL="https://github.com/Alihuseyn-ibrahimov/masterai.git"
BRANCH="${BRANCH:-main}"
SRV=/opt/masterai
WEB=/opt/masterai-web
DOMAINS=(masterai.prdostu.com api.masterai.prdostu.com)

step() { echo; echo "=== $* ==="; }

[ "$(id -u)" -eq 0 ] || { echo "XETA: root kimi işlət" >&2; exit 1; }
if [ ! -f "$SRV/.env" ] && [ -z "${GROQ_API_KEY:-}" ]; then
  echo "XETA: ilk qurulmada GROQ_API_KEY verilməlidir" >&2
  exit 1
fi

step "1/9 firewall (22, 80, 443)"
# 80 olmasa certbot-un HTTP-01 yoxlaması "likely firewall problem" ilə
# sınır (köhnə serverdə real baş verib).
apt-get update -qq
apt-get install -y -qq ufw
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

step "2/9 swap + jurnal limiti"
# Chrome (link materialı) yaddaşı yeyir; köhnə serverdə swap-sız qalmışdı.
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=150M\n' > /etc/systemd/journald.conf.d/masterai.conf
systemctl restart systemd-journald

step "3/9 sistem paketləri"
# tesseract-ocr-aze: pipeline "aze+eng" işlədir, paket olmasa OCR sükutla
# ingilis modelinə düşür. Chrome: snap chromium Selenium ilə İŞLƏMİR
# (AppArmor, "DevToolsActivePort file doesn't exist"), rəsmi .deb lazımdır.
apt-get install -y -qq git curl rsync python3-venv python3-pip nginx \
  certbot python3-certbot-nginx tesseract-ocr tesseract-ocr-aze
if ! command -v google-chrome >/dev/null 2>&1; then
  curl -fsSL -o /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  apt-get install -y -qq /tmp/chrome.deb
  rm -f /tmp/chrome.deb
fi
apt-get clean

step "4/9 kod ($REPO_URL, $BRANCH)"
if [ -d "$SRV/.git" ]; then
  git -C "$SRV" fetch -q origin "$BRANCH"
  git -C "$SRV" checkout -q "$BRANCH"
  git -C "$SRV" pull -q --ff-only origin "$BRANCH"
else
  git clone -q -b "$BRANCH" "$REPO_URL" "$SRV"
fi
git -C "$SRV" log --oneline -1

step "5/9 venv + asılılıqlar"
cd "$SRV"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt
mkdir -p "$SRV/data/uploads"

step "6/9 .env"
if [ -f "$SRV/.env" ]; then
  echo ".env artıq var - TOXUNULMUR (JWT_SECRET dəyişməsin)"
else
  gen() { .venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'; }
  ADMIN_API_KEY_VAL="${ADMIN_API_KEY:-$(gen)}"
  {
    echo "GROQ_API_KEY=$GROQ_API_KEY"
    [ -n "${ANTHROPIC_API_KEY:-}" ] && echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY"
    echo "JWT_SECRET=${JWT_SECRET:-$(gen)}"
    echo "ADMIN_API_KEY=$ADMIN_API_KEY_VAL"
    echo "ADMIN_WEBHOOK_URL=${ADMIN_WEBHOOK_URL:-}"
    # HƏR baza data/-dadır: backup bir qovluğu götürür, heç nə itmir.
    for pair in USERS:users CHATS:chats MESSAGES:messages MATERIALS:materials \
                QUESTIONS:questions QUIZ_SESSIONS:quiz_sessions \
                QUIZ_ATTEMPTS:quiz_attempts FRIENDSHIPS:friendships \
                QUESTION_SETS:question_sets LIVE_SESSIONS:live_sessions \
                HOMEWORK:homework BADGES:badges \
                CHAT_JOIN_REQUESTS:chat_join_requests SUMMARIES:summaries; do
      echo "${pair%%:*}_DB_PATH=$SRV/data/${pair##*:}.db"
    done
    echo "MATERIAL_UPLOAD_DIR=$SRV/data/uploads"
  } > "$SRV/.env"
  chmod 600 "$SRV/.env"
  echo "ADMIN_API_KEY (n8n 'Gündəlik Statistika' üçün): $ADMIN_API_KEY_VAL"
fi

step "7/9 systemd"
cp "$SRV/deploy/masterai.service" /etc/systemd/system/masterai.service
systemctl daemon-reload
systemctl enable -q masterai
systemctl restart masterai
for _ in $(seq 1 20); do
  curl -sf http://127.0.0.1:8110/health >/dev/null && break
  sleep 1
done
curl -sf http://127.0.0.1:8110/health || { journalctl -u masterai -n 40 --no-pager; exit 1; }
echo

step "8/9 statik sayt + nginx"
rsync -a --delete --exclude tests "$SRV/web/" "$WEB/"
chmod -R a+rX "$WEB"
# certbot artıq HTTPS əlavə edibsə, faylı yenidən yazmaq onu silər.
if [ ! -f /etc/nginx/sites-available/masterai ] || ! grep -q ssl_certificate /etc/nginx/sites-available/masterai; then
  cp "$SRV/deploy/nginx-masterai.conf" /etc/nginx/sites-available/masterai
fi
ln -sf /etc/nginx/sites-available/masterai /etc/nginx/sites-enabled/masterai
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

step "9/9 HTTPS"
if [ "${SKIP_CERTBOT:-}" = "1" ]; then
  echo "atlandı (SKIP_CERTBOT=1)"
elif grep -q ssl_certificate /etc/nginx/sites-available/masterai; then
  echo "sertifikat artıq var"
else
  args=()
  for d in "${DOMAINS[@]}"; do args+=(-d "$d"); done
  certbot --nginx "${args[@]}" --non-interactive --agree-tos \
    --register-unsafely-without-email --redirect \
  || echo "(certbot uğursuz - DNS hələ yeni IP-yə yayılmayıb. Sonra: certbot --nginx ${args[*]})"
fi

echo
echo "=== BİTDİ ==="
echo "Server IP: $(curl -s https://api.ipify.org || echo '?')"
echo "Yoxla:  curl -s https://masterai.prdostu.com/health"
echo "Yeniləmə üçün eyni skripti yenidən işlət - data və .env qalır."
