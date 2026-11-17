# Kurs Kassası demosunu serverə qoymaq

Nəticə: `https://kassa.prdostu.com` ünvanında sintetik pilot kursu (10 qrup, ~190 şagird)
ilə işləyən Kassa paneli. Parol arxasındadır, axtarış sistemlərinə bağlıdır.

**Produksiyaya toxunmur.** `masterai.prdostu.com` (`/opt/masterai`, port 8110, öz
bazaları) olduğu kimi qalır. Demo ayrı qovluqdadır və ayrı prosesdir:

| | Produksiya | Kassa demosu |
|---|---|---|
| Kod | `/opt/masterai` | `/opt/kassa-demo/app` (ayrı klon, ayrı venv) |
| Data | `/opt/masterai/data` | `/opt/kassa-demo/data` (`deploy/kassa_demo.py` yaradır) |
| Servis | `masterai`, 127.0.0.1:8110 | `kassa-demo`, 127.0.0.1:8111, yaddaş ≤400 MB |
| Sayt | `/opt/masterai-web` | `/opt/kassa-demo/web` (surət, API ünvanı dəyişdirilib) |
| nginx | `sites-available/masterai` | `sites-available/kassa-demo` (ayrı fayl) |

**2 GB yaddaş:** demo ~170 MB, eval ~190 MB işlədir (lokal ölçülüb). `kassa-demo.service`
`MemoryMax=400M` ilə məhdudlaşdırılıb: nəsə şişsə yalnız demo dayanır.

**Necə işləyirik:** hər addımı serverdə SSH ilə işlət, çıxışı olduğu kimi çata yapışdır.
«Gözlənilən» ilə üst-üstə düşmürsə növbəti addıma KEÇMƏ.

---

## 0. İlkin yoxlama (heç nə dəyişmir)

Öz kompüterindən: `ssh root@SERVER_IP`, sonra:

```bash
hostname; df -h / | tail -1; free -m | sed -n 2,3p
systemctl is-active masterai nginx
ls /opt
curl -s 127.0.0.1:8110/health; echo
ss -ltn | grep -c ':8111 '
curl -s https://api.ipify.org; echo
```

Gözlənilən:

```
ubuntu-s-1vcpu-2gb-70gb-intel-fra1
/dev/vda1   68G  ...  ...  NN% /        ← NN 80-dən azdır
Mem:   1967  ...  ...  ...  ...  ≥600   ← sonuncu sütun (available)
Swap:  2047  ...
active
active
masterai  masterai-web
{"status":"ok"}
0                                       ← 8111 portu boşdur
SERVER_IP                               ← 1-ci addım üçün yadda saxla
```

`/opt/masterai` yoxdursa (məs. köhnə `/opt/pr-agent/repo` qurulması), DAYAN və çıxışı göndər.

## 1. DNS: `kassa.prdostu.com` → server

`prdostu.com`-un DNS-ində (`masterai` qeydini harada yaratmısansa, orada) yeni qeyd:

| Tip | Ad | Dəyər |
|---|---|---|
| A | `kassa` | 0-cı addımdakı SERVER_IP |

Yayılması bir neçə dəqiqə çəkir. 2-7-ci addımlar bu müddətdə gedə bilər. Yoxlama (8-ci
addımdan əvvəl):

```bash
getent hosts kassa.prdostu.com
```

Gözlənilən: `SERVER_IP  kassa.prdostu.com`. Boşdursa hələ yayılmayıb.

## 2. Kod

```bash
mkdir -p /opt/kassa-demo
git clone -q https://github.com/Alihuseyn-ibrahimov/masterai.git /opt/kassa-demo/app
git -C /opt/kassa-demo/app log --oneline -1
ls /opt/kassa-demo/app/deploy/kassa-demo.service
```

Gözlənilən: son commit sətri (main) və `/opt/kassa-demo/app/deploy/kassa-demo.service`.
`already exists` yazsa: `git -C /opt/kassa-demo/app pull --ff-only`.

## 3. venv + asılılıqlar (3-6 dəqiqə)

```bash
cd /opt/kassa-demo/app
python3 -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt scikit-learn
.venv/bin/python -c "import fastapi, sklearn; print('ok', sklearn.__version__)"
```

Gözlənilən: son sətir `ok 1.x.x`. `scikit-learn` evalın şagird itkisi hissəsi üçündür
(~40 MB, torch QOYULMUR). Çıxışda `Killed` görsən: `free -m` göndər.

## 4. Pilot datası (sintetik kurs)

```bash
cd /opt/kassa-demo/app
.venv/bin/python deploy/kassa_demo.py --data-dir /opt/kassa-demo/data
chmod 600 /opt/kassa-demo/data/demo.env
ls /opt/kassa-demo/data | head -3
```

Gözlənilən (rəqəmlər günə görə bir az dəyişir):

```
Pilot kursu hazırdır: /opt/kassa-demo/data (bu gün: 2026-11-17)
  10 qrup, 186 şagird (indi qrupda 91), getmiş 50 {...}
  1064 ödəniş (22 qismən), 7128 davamiyyət, 63 xərc qeydi; CSV: /opt/kassa-demo/data/tables
  giriş: rehber@kassa-demo.example.com / XXXXXXXXXXXX
  server: ...
badges.db
chat_join_requests.db
chats.db
```

**`giriş:` sətrindəki şifrəni yadda saxla** (Kassaya giriş üçün). Çata yapışdıranda
şifrəni `***` ilə əvəz et. Skript bazası olan qovluğa yazmır: yenidən yaratmaq üçün
əvvəl `systemctl stop kassa-demo; mv /opt/kassa-demo/data /opt/kassa-demo/data.old`.

## 5. Demo backend (systemd)

```bash
cp /opt/kassa-demo/app/deploy/kassa-demo.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now kassa-demo
sleep 5
systemctl is-active kassa-demo
curl -s 127.0.0.1:8111/health; echo
curl -s 127.0.0.1:8110/health; echo
systemctl show kassa-demo -p MemoryCurrent
```

Gözlənilən:

```
active
{"status":"ok"}          ← demo
{"status":"ok"}          ← produksiya, dəyişməyib
MemoryCurrent=1xxxxxxxx  ← ~150-200 MB
```

`failed` olsa: `journalctl -u kassa-demo -n 40 --no-pager` göndər.

## 6. Saytın surəti (API ünvanı demoya yönəldilir)

Saytın `config.js`-i API-ni `masterai.prdostu.com`-da axtarır. Surətdə bu
`kassa.prdostu.com` olur, yoxsa demo səhifələri PRODUKSİYA bazasına müraciət edərdi.

```bash
rm -rf /opt/kassa-demo/web
cp -a /opt/kassa-demo/app/web /opt/kassa-demo/web
rm -rf /opt/kassa-demo/web/tests
sed -i 's#masterai.prdostu.com#kassa.prdostu.com#' /opt/kassa-demo/web/assets/js/config.js
chmod -R a+rX /opt/kassa-demo/web
grep -n "BASE_URL =" /opt/kassa-demo/web/assets/js/config.js
```

Gözlənilən (hər iki sətirdə `kassa`):

```
11:export const API_BASE_URL = 'https://kassa.prdostu.com';
12:export const WS_BASE_URL = 'wss://kassa.prdostu.com';
```

## 7. Parol + nginx

Saytın səhifələri parol (basic auth) arxasındadır. API-də bu parol YOXDUR, çünki tətbiq
hər sorğuda öz giriş tokenini eyni başlıqda göndərir. API onsuz da tətbiqin girişi ilə
qorunur, Kassa yalnız rəhbərə açılır, qeydiyyat isə bağlıdır.

```bash
KASSA_PW=$(openssl rand -base64 12); echo "sayt parolu: demo / $KASSA_PW"
printf 'demo:%s\n' "$(openssl passwd -apr1 "$KASSA_PW")" > /etc/nginx/kassa-demo.htpasswd
chown root:www-data /etc/nginx/kassa-demo.htpasswd; chmod 640 /etc/nginx/kassa-demo.htpasswd
cp /etc/nginx/sites-available/masterai /root/nginx-masterai.backup-$(date +%F)
cp /opt/kassa-demo/app/deploy/nginx-kassa-demo.conf /etc/nginx/sites-available/kassa-demo
ln -sf /etc/nginx/sites-available/kassa-demo /etc/nginx/sites-enabled/kassa-demo
nginx -t && systemctl reload nginx
curl -s -o /dev/null -w "produksiya: %{http_code}\n" https://masterai.prdostu.com/health
```

Gözlənilən:

```
sayt parolu: demo / XXXXXXXXXXXXXXXX     ← yadda saxla, çata YAPIŞDIRMA
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
produksiya: 200
```

`nginx -t` xəta versə reload OLMUR (produksiya köhnə konfiqlə işləməyə davam edir).
Onda faylı söndür və xətanı göndər:
`rm /etc/nginx/sites-enabled/kassa-demo && nginx -t`.

## 8. HTTPS (DNS yayılandan sonra)

```bash
getent hosts kassa.prdostu.com
certbot --nginx -d kassa.prdostu.com --non-interactive --agree-tos --register-unsafely-without-email --redirect
curl -s -o /dev/null -w "parolsuz sayt: %{http_code}\n" https://kassa.prdostu.com/kassa.html
curl -s -o /dev/null -w "parolla sayt:  %{http_code}\n" -u "demo:$KASSA_PW" https://kassa.prdostu.com/kassa.html
curl -s -w "  api: %{http_code}\n" https://kassa.prdostu.com/health
curl -s -o /dev/null -w "qeydiyyat:     %{http_code}\n" -X POST https://kassa.prdostu.com/auth/register
curl -s -o /dev/null -w "produksiya:    %{http_code}\n" https://masterai.prdostu.com/health
```

Gözlənilən:

```
SERVER_IP  kassa.prdostu.com
...
Successfully deployed certificate for kassa.prdostu.com to /etc/nginx/sites-available/kassa-demo
Congratulations! You have successfully enabled HTTPS on https://kassa.prdostu.com
parolsuz sayt: 401
parolla sayt:  200
{"status":"ok"}  api: 200
qeydiyyat:     403
produksiya:    200
```

certbot yalnız `kassa-demo` faylını dəyişir. SSH sessiyası bağlanıbsa `$KASSA_PW` boş olar:
«parolla sayt» sətrində parolu əl ilə yaz.

## 9. Brauzerdə

1. `https://kassa.prdostu.com/giris.html` → brauzer parol soruşur: `demo` / 7-ci addımın parolu.
2. Giriş: `rehber@kassa-demo.example.com` / 4-cü addımın şifrəsi.
3. «Hesabatlar» → «Kassa» (və ya birbaşa `https://kassa.prdostu.com/kassa.html`).

Gözlənilən (lokal sınaqda belə idi): dörd kart (Gözlənilən ~10 720 AZN, Yığılan ~76%,
Borc ~25 nəfər, Xalis), altında «Borclular» siyahısı, «7 nəfər 2+ aydır ödəmir».
Ekran şəklini çata göndər.

## 10. Eval: `python3 -m evals.kassa --live`

Bu, CLI əmri deyil, **repo kökündən** modul kimi işləyir. LLM açarı produksiyanın
`.env`-indən yalnız oxunur (bütün `.env` yüklənmir: onun baza yolları produksiyanındır).
Qəbzlər sintetikdir, ona görə Groq-a göndərmək olar (`RECEIPT_ALLOW_EXTERNAL_LLM=true`).
`--receipts 10`: LLM hər qəbz növündən 10 qəbzdə ölçülür (60 sorğu, ~2-4 dəqiqə).
Hamısı (360 sorğu) Groq-un pulsuz limitinə dəyir.

```bash
cd /opt/kassa-demo/app
export GROQ_API_KEY="$(grep '^GROQ_API_KEY=' /opt/masterai/.env | cut -d= -f2-)"
export ANTHROPIC_API_KEY="$(grep '^ANTHROPIC_API_KEY=' /opt/masterai/.env | cut -d= -f2-)"
mkdir -p /opt/kassa-demo/eval
RECEIPT_ALLOW_EXTERNAL_LLM=true nice -n 10 .venv/bin/python3 -m evals.kassa --live --receipts 10 \
  --out /opt/kassa-demo/eval/kassa-live-$(date +%F).md
```

Gözlənilən: hesabat ekrana çıxır və fayla yazılır. Əsas sətirlər:

```
# Kurs Kassası: eval hesabatı (live, ...)
## 1. Şagird itkisi: zəng siyahısı ...           ← cədvəl (sklearn var)
## 1b. Pilot datası ...                          ← cədvəl + «real ad LLM-ə gedən mətndə: 0»
## 2. Qəbz oxuyucusu: bütün sahələr düz
| Qaydalar | 92% | 50% |
| LLM + yoxlama + qaydalar | ..% | ..% |           ← LLM yolunun nəticəsi
LLM yolu seçmədə ölçülüb (`--receipts`): görülən 40, görülməyən 20 qəbz.
Mənbə (görülməyən): {'llm': 15, 'rules': .., 'none': ..}, 1.2 san/qəbz.   ← 'llm' 0-dan böyük
## 4. «Kassaya sual» ... Keçildi: autogen_agentchat quraşdırılmayıb
## 5. Aylıq hesabat ... Keçildi: crewai quraşdırılmayıb
Offline hədlər: hamısı keçdi.
```

4 və 5-in «keçildi» olması bu addımda NORMALDIR: CrewAI (~1 GB) və AutoGen serverə
qoyulmur (`requirements-agents.txt`, `requirements-autogen.txt`), sahibin kompüterində
işləyir. `Mənbə` sətrində `'llm': 0` görsən LLM çağırılmayıb (açar oxunmayıb və ya Groq
xəta verib): `echo ${#GROQ_API_KEY}` (0-dan böyük olmalıdır) çıxışını göndər. Hesabat faylını götürmək: `cat /opt/kassa-demo/eval/kassa-live-*.md`.

### 10b. (İstəyə görə) «Kassaya sual»ı da serverdə ölçmək

AutoGen CrewAI-dan yüngüldür, ayrı venv-də qoyula bilər (~5 dəqiqə, ~300 MB disk):

```bash
cd /opt/kassa-demo/app
python3 -m venv /opt/kassa-demo/venv-autogen
/opt/kassa-demo/venv-autogen/bin/pip install -q -r requirements-autogen.txt scikit-learn
RECEIPT_ALLOW_EXTERNAL_LLM=true nice -n 10 /opt/kassa-demo/venv-autogen/bin/python3 -m evals.kassa --live \
  --receipts 10 --out /opt/kassa-demo/eval/kassa-live-autogen-$(date +%F).md
```

Gözlənilən: 4-cü bölmədə «Keçildi» əvəzinə cavab dəqiqliyi cədvəli.

---

## Yeniləmə

```bash
git -C /opt/kassa-demo/app pull --ff-only
/opt/kassa-demo/app/.venv/bin/pip install -q -r /opt/kassa-demo/app/requirements.txt
systemctl restart kassa-demo
# sonra 6-cı addımı təkrarla (saytın surəti)
```

## Geri qaytarma (demonu tam söndürmək)

```bash
systemctl disable --now kassa-demo
rm /etc/nginx/sites-enabled/kassa-demo
nginx -t && systemctl reload nginx
curl -s -o /dev/null -w "produksiya: %{http_code}\n" https://masterai.prdostu.com/health
```

Qovluq (`/opt/kassa-demo`) qalır, produksiya dəyişmir. Data sintetikdir: görüşdə də belə deyilir.
