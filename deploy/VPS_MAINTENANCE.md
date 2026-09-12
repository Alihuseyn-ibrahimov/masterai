# VPS baxımı: disk təmizliyi + restart

`<SERVER_IP>` (DigitalOcean, 8.65 GB disk, 512 MB RAM). **Bu maşında
BEŞ layihə var:** masterai, dildostu-live, masternr1 (aktiv pilot),
n8n, mediapulse (`saas_core`, nazirlik müştərisi). Diskin dolması və ya
səhv restart hamısını **birdən** öldürür — bax `CLAUDE.md`, "Dərs: real
deploy zamanı rast gəlinən tələlər", bənd 4 və 6.

Disk üçüncü dəfədir problem yaradır. Kök həll diskin böyüdülməsidir
(DigitalOcean-da resize), aşağıdakılar isə vaxt qazandırır.

---

## 0. ÖLÇ (əvvəl bu, sonra hər şey)

```bash
cd /opt/pr-agent/repo/masterai && bash deploy/vps_disk_report.sh
```

Heç nə silmir. Bu addımı ATLAMA: keçmişdə "yer açmaq" üçün əlavə edilən
2 GB swap faylı diski TAM doldurub `masterai`-ni crash-loop-a salmışdı.
Silməyə nə lazım olduğunu hesabat göstərir, təxmin yox.

Hesabatda ən vacib sətir **`is-enabled`**-dir (aşağı, bölmə 3).

---

## 1. TƏMİZLƏ — üç təbəqə, riskə görə sıralanmış

### Təbəqə A — tam təhlükəsiz (keşdir, özü yenidən yaranır)

```bash
rm -rf /root/.cache/selenium /root/.cache/pip
apt clean                           # /var/cache/apt/archives
journalctl --vacuum-size=50M
```

**DİQQƏT — 2026-09-12 ölçməsi bu təbəqənin dəyərini AZ göstərdi.**
Əvvəl burada selenium keşinin 845 MB-a çatdığı yazılmışdı və ilk
təxminim məhz o idi; real ölçmə isə **22 MB** verdi, jurnal onsuz da
`SystemMaxUse=150M` ilə məhdudlaşdırılıb (127.9 MB). Yəni bütün A
təbəqəsi cəmi ~50-150 MB qaytarır — 90% dolu diskdə bu, çıxış yolu
DEYİL. Əsl yer B və C təbəqələrində, həqiqi böyük qovluqlarda
(`/var/lib`, `/usr/src`, köhnə kernellər) və son nəticədə diskin
böyüdülməsindədir.

Dərs: "keçən dəfə bu şişmişdi" HESABAT DEYİL. Həmişə bölmə 0-dan başla.

Jurnalın limiti yoxdursa, birdəfəlik təyin et (yenidən dolmasın):

```bash
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=150M\n' > /etc/systemd/journald.conf.d/size.conf
systemctl restart systemd-journald
```

### Təbəqə B — QƏRAR tələb edir (data, keş deyil)

```bash
ls -lh /root/backup-*.db /root/masterai-backup/*/ 2>/dev/null
```

Backup-lar **sənin qərarındır**. Qayda təklifi: **son 2 backup-ı
saxla**, qalanını sil. Ən son təmirin backup-ı
(`/root/backup-live-2026-09-12-0827.db`) hələ SAXLANILMALIDIR —
sessiya #31 birləşməsinin tək geri yolu odur.

### Təbəqə C — YALNIZ RESTARTDAN SONRA

```bash
apt autoremove --purge    # köhnə kernelləri silir
```

Restartdan **əvvəl** etmə: sistem hazırda yüklü kernellə işləyir və yeni
kernel hələ sınanmamışdır. Restart uğurlu olandan sonra bu, adətən ən
çox yer qaytaran addımdır.

### Sonra yenidən ölç

```bash
bash deploy/vps_disk_report.sh | head -5
```

**Hədəf: `/` 80%-dən aşağı.** 90%+ qalırsa, təmizlik kifayət etmir —
diski böyütmək lazımdır, başqa yol yoxdur.

---

## 2. Restart NƏ VAXT

`*** System restart required ***` kernel/kitabxana yeniləməsindən gəlir.
Gecikdirmək təhlükəsizlik yaması olmadan işləmək deməkdir, ona görə
planlaşdırılmalıdır — amma ixtiyari vaxtda yox.

| Servis | Kim əziyyət çəkir | Həssas vaxt |
|---|---|---|
| mediapulse (`saas_core`) | dövlət qurumu | iş saatları 09:00-18:00 |
| masternr1 | real müştərilər (WhatsApp/Instagram) | axşam, müştəri aktivliyi |
| masterai | tələbələr, canlı dərs sessiyaları | axşam + dərs vaxtı |
| n8n | gündəlik statistika + xəta bildirişləri | öz cron saatı |
| dildostu-live | test istifadəçiləri | ən az həssas |

**Təklif olunan pəncərə: 02:00-03:00 (Bakı vaxtı).** Hər beş servis üçün
ən sakit saat. Dərs günü səhəri deyil — problem çıxsa düzəltməyə vaxt
qalsın.

**ƏVVƏLCƏ n8n-in cron saatını yoxla** — gündəlik statistika workflow-u
məhz o pəncərədə işləyirsə, bir saat sürüşdür.

Gözlənilən fasilə: reboot özü ~30-60 saniyə, servislərin qalxması ilə
birlikdə **adətən 2 dəqiqədən az**. Planda isə 10 dəqiqə saxla — geri
qalxmayan bir servis olsa vaxt lazım olacaq.

---

## 3. Restartdan ƏVVƏL — pre-flight

**(a) Ən vacib yoxlama: hər servis `enabled`-dir?**

Siyahını **maşından** götür, sənəddən YOX. 2026-09-12-də bu sənəddə
`masternr1-web`, `masternr1-celery`, `n8n` yazılmışdı — maşında belə
servis YOXDUR (adlar layihə sənədlərindən götürülmüşdü). Əvəzində
`gunicorn.service`, `cloudflared.service` var. Adını bilmədiyin servisi
yoxlaya bilmirsən, yəni restartdan sonra qalxıb-qalxmadığını da bilmirsən.

```bash
# 1) İŞLƏYƏN bütün servislər (sistem servisləri xaric):
systemctl list-units --type=service --state=running --no-legend --no-pager \
  | awk '{print $1}' | grep -vE "systemd-|dbus|cron|ssh|getty|polkit|rsyslog|\
unattended|multipathd|udisks|networkd|resolved|logind|journald|accounts|fwupd|\
ModemManager|snap\.|user@"

# 2) hər birinin enabled vəziyyəti:
for s in $(systemctl list-units --type=service --state=running --no-legend --no-pager \
           | awk '{print $1}'); do
  printf '%-35s %s\n' "$s" "$(systemctl is-enabled $s 2>&1)"
done | grep -v " enabled$"     # yalnız PROBLEMLİ olanlar görünür
```

İkinci əmr **boş çıxsa, hər şey qaydasındadır**. Nə görünürsə —
`disabled`, `static`, `linked` — restartdan əvvəl araşdırılmalıdır.

`disabled` olan servis **restartdan sonra özü qalxmır və heç bir xəta
vermir** — sükutla ölür. Bu, restartın ən böyük riskidir. `disabled`
tapılsa, restartdan ƏVVƏL düzəlt:

```bash
systemctl enable <servis>
```

**(b) Swap fstab-dadır?**

```bash
swapon --show && grep swap /etc/fstab
```

`/swapfile` işləyir, amma `fstab`-da yoxdursa, restartdan sonra
QAYITMIR — 512 MB RAM-da bu, emal zamanı OOM deməkdir. Yoxdursa əlavə et:

```bash
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

**(c) Bütün bazaların backup-ı.** DİQQƏT: bazalar İKİ yerdədir —
`data/` VƏ iş qovluğunun kökü (`live_sessions`, `question_sets`,
`homework`, `badges` kökdədir). Yalnız `data/`-nı götürmək 4 bazanı
itirmək deməkdir.

```bash
D=/root/prereboot-$(date +%F-%H%M) && mkdir -p $D
cp -a /opt/pr-agent/repo/masterai/*.db /opt/pr-agent/repo/masterai/data/*.db $D/ 2>/dev/null
ls -lh $D | tail -20
```

Digər layihələrin bazaları üçün öz sənədlərinə bax (`masternr1/DEPLOY.md`,
`saas_core/`). **masternr1 aktiv pilotdur — onun datası da götürülməlidir.**

**(d) Disk 80%-dən aşağıdır?** Dolu diskdə restart risklidir: servis
qalxarkən müvəqqəti fayl yaza bilməz («No usable temporary directory
found» — bu maşında real baş verib).

---

## 4. Restart

```bash
reboot
```

Sonra ~60 saniyə gözlə və yenidən SSH ilə qoş.

---

## 5. Restartdan SONRA — MƏNBƏDƏN yoxla

Ekrana baxıb "qalxdı" demək kifayət deyil. Hər servis ayrıca:

Restartdan ƏVVƏL işləyən servislərin siyahısını fayla yaz, sonra
müqayisə et — yaddaşa güvənmə:

```bash
# ƏVVƏL (restartdan qabaq):
systemctl list-units --type=service --state=running --no-legend --no-pager \
  | awk '{print $1}' | sort > /root/servis-evvel.txt

# SONRA (restartdan sonra):
systemctl list-units --type=service --state=running --no-legend --no-pager \
  | awk '{print $1}' | sort > /root/servis-sonra.txt
diff /root/servis-evvel.txt /root/servis-sonra.txt && echo "FƏRQ YOXDUR"
swapon --show
df -h /
```

`<` ilə başlayan sətir **qalxmayan servisdir** — ən çox ehtiyac
duyulan yoxlama budur.

Sonra hər sayt **kənardan** (HTTP status):

```bash
for u in https://masterai.prdostu.com/health https://mediapulse.az \
         https://n8n.prdostu.com; do
  printf '%-45s %s\n' "$u" "$(curl -s -o /dev/null -w '%{http_code}' $u)"
done
```

masternr1 üçün HTTP yoxlaması kifayət deyil — o, WhatsApp/Instagram
webhook-larına cavab verir. **Real yoxlama: pilot nömrəsinə bir test
mesajı göndər və cavab gəldiyini gör.** Aktiv pilotdur, bunu atlamaq
olmaz.

masterai üçün funksional yoxlama:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://masterai.prdostu.com/index.html
```

Hər şey qaydasındadırsa, indi Təbəqə C:

```bash
apt autoremove --purge && df -h /
```

---

## 6. Nə vaxt bu sənəd kifayət etmir

Təmizlikdən sonra disk yenə 85%+ qalırsa, bu, baxım problemi deyil —
**tutum problemidir**. O halda:

- DigitalOcean-da diski böyüt (resize, restart tələb edir), VƏ YA
- servisləri ayır (n8n və ya dildostu-live başqa maşına)

Çatda fayl/səs mesajı funksiyası (planlaşdırılan alt-layihə) **bu qərar
verilməmiş başlana bilməz** — istifadəçi faylları diskə yazılır və
hazırda ~1 GB boş yer var.
