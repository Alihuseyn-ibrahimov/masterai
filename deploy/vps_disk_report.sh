#!/usr/bin/env bash
# VPS disk və restart hazırlığı HESABATI — HEÇ NƏ SİLMİR, HEÇ NƏ DƏYİŞMİR.
#
# NİYƏ ÖLÇMƏ AYRI SKRİPTDİR: bu maşında bir dəfə "yer açmaq" üçün əlavə
# edilən 2GB swap faylı diski TAM doldurub `masterai` servisini
# çökdürdü (bax CLAUDE.md, "Dərs: real deploy zamanı rast gəlinən
# tələlər", bənd 6). Ona görə əvvəl ÖLÇ, sonra sil.
#
# Maşında BEŞ layihə var: masterai, dildostu-live, masternr1 (aktiv
# pilot), n8n, mediapulse (saas_core — nazirlik müştərisi). Diskin
# dolması və ya səhv restart hamısını birdən öldürür.
#
# İşlətmə:  bash deploy/vps_disk_report.sh

set -u

say() { printf '\n=== %s ===\n' "$1"; }

say "DİSK"
df -h /

say "ƏN BÖYÜK QOVLUQLAR (/ altında, 2 səviyyə)"
du -xh --max-depth=2 / 2>/dev/null | sort -rh | head -15

say "JURNAL"
if command -v journalctl >/dev/null 2>&1; then
  journalctl --disk-usage
  grep -h "^SystemMaxUse" /etc/systemd/journald.conf /etc/systemd/journald.conf.d/*.conf 2>/dev/null \
    || echo "SystemMaxUse təyin edilməyib — jurnal sərbəst böyüyür"
else
  echo "journalctl yoxdur"
fi

say "KEŞLƏR (təhlükəsiz silinə bilənlər)"
for p in /root/.cache/selenium /root/.cache/pip /root/.cache/ms-playwright \
         /root/.npm /var/cache/apt/archives /tmp /var/tmp; do
  [ -e "$p" ] && du -sh "$p" 2>/dev/null
done

say "BACKUP FAYLLARI (əl ilə yaradılmış — nə vaxt silinəcəyi QƏRARDIR)"
du -sh /root/masterai-backup 2>/dev/null
ls -lh /root/backup-*.db 2>/dev/null | awk '{print $5, $9}'
find /root -maxdepth 2 -name "*.db" -mtime +14 2>/dev/null | sed 's/^/  14 gündən köhnə: /'

say "KÖHNƏ KERNELLƏR (restartdan SONRA silinməlidir, əvvəl YOX)"
if command -v dpkg >/dev/null 2>&1; then
  dpkg -l 2>/dev/null | awk '/^ii  linux-(image|headers)-[0-9]/ {print "  " $2}'
  echo "  işləyən kernel: $(uname -r)"
fi

say "DOCKER (varsa)"
command -v docker >/dev/null 2>&1 && docker system df 2>/dev/null || echo "docker yoxdur"

say 'SERVİSLƏR — is-enabled ƏN VACİB SÜTUNDUR'
echo "(disabled servis RESTARTDAN SONRA ÖZÜ QALXMIR — sükutla ölür)"
if command -v systemctl >/dev/null 2>&1; then
  for svc in masterai dildostu-live masternr1-web masternr1-celery pr-agent \
             n8n nginx; do
    if systemctl list-unit-files "${svc}.service" >/dev/null 2>&1 \
       && systemctl cat "$svc" >/dev/null 2>&1; then
      printf '  %-20s enabled=%-10s active=%s\n' "$svc" \
        "$(systemctl is-enabled "$svc" 2>&1)" "$(systemctl is-active "$svc" 2>&1)"
    else
      printf '  %-20s (belə servis yoxdur)\n' "$svc"
    fi
  done
  echo "  --- yuxarıda olmayan, işləyən digər servislər:"
  systemctl list-units --type=service --state=running --no-legend --no-pager 2>/dev/null \
    | awk '{print "    " $1}' \
    | grep -vE "masterai|dildostu-live|masternr1|pr-agent|n8n|nginx|systemd-|dbus|cron|ssh|getty|polkit|rsyslog|unattended|multipathd|udisks|networkd|resolved|logind|journald|accounts-daemon|snapd|do-agent|qemu|irqbalance|atd|chrony" \
    || true
fi

say "SWAP (restartdan sonra qayıdır?)"
_swap="$(swapon --show 2>/dev/null)"
if [ -n "$_swap" ]; then echo "$_swap"; else echo "swap YOXDUR (512MB RAM-da risklidir)"; fi
grep -c swap /etc/fstab 2>/dev/null | sed 's/^/  fstab-da swap sətri sayı: /'
echo "  (fstab-da YOXDURSA, swap restartdan sonra QAYITMIR)"

say "RESTART TƏLƏB OLUNUR?"
if [ -f /var/run/reboot-required ]; then
  echo "BƏLİ"
  cat /var/run/reboot-required.pkgs 2>/dev/null | sed 's/^/  səbəb: /'
else
  echo "xeyr"
fi

say "UPTIME"
uptime
