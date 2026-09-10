# MasterAI — veb saytın deploy skripti (Windows).
#
# `saas_core/deploy.ps1`-in TEST QAPISI naxışı ilə: testlər keçməsə
# server ÜMUMİYYƏTLƏ toxunulmur.
#
# Build addımı YOXDUR — fayllar olduğu kimi köçürülür (npm/bundler yox).
#
# İşlətmək:
#     cd masterai
#     powershell -ExecutionPolicy Bypass -File deploy\deploy_web.ps1

$ErrorActionPreference = "Stop"

$KEY    = "$env:USERPROFILE\.ssh\id_rsa"
$SERVER = "root@<SERVER_IP>"
$LOCAL  = Split-Path -Parent $PSScriptRoot     # masterai/
$REMOTE = "/opt/masterai-web"

function Fail($message) {
    Write-Host "XETA: $message" -ForegroundColor Red
    exit 1
}

# ── 1. Test qapısı ───────────────────────────────────────────────────
Write-Host "Backend + veb testleri isledilir..." -ForegroundColor Cyan
& "$LOCAL\.venv\Scripts\python.exe" -m pytest -q
if ($LASTEXITCODE -ne 0) { Fail "pytest ugursuz oldu - deploy DAYANDIRILDI" }

if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "JavaScript testleri isledilir..." -ForegroundColor Cyan
    & node --test (Get-ChildItem "$LOCAL\web\tests\*.test.js" | ForEach-Object { $_.FullName })
    if ($LASTEXITCODE -ne 0) { Fail "JS testleri ugursuz oldu - deploy DAYANDIRILDI" }
} else {
    Write-Host "Node tapilmadi - JS testleri atlandi." -ForegroundColor Yellow
}

# ── 2. Disk yoxlamasi ────────────────────────────────────────────────
# Bu VPS-de disk dolmasi eweller masterai-ni COKDURUB ve masternr1
# (aktiv pilot) daxil dord servisi riske atib. Kocurmeden EVVEL
# yoxlamaq mecburidir (bax masterai/CLAUDE.md, "Ders: real deploy telelerи").
Write-Host "Serverin disk veziyyeti yoxlanilir..." -ForegroundColor Cyan
$usage = ssh -i $KEY $SERVER "df --output=pcent / | tail -1 | tr -dc '0-9'"
Write-Host "  Disk istifadesi: $usage%"
if ([int]$usage -ge 98) { Fail "Disk $usage% doludur - kocurme servisleri riske atar" }

# ── 3. Kocurme ───────────────────────────────────────────────────────
Write-Host "Fayller kocurulur..." -ForegroundColor Cyan
# QEYD: joker (`web\*`) ISLEDILMIR — yolda bosluq olanda PowerShell onu
# genislendirmir ve scp herfi `*` gorur. Butov qovlugu kocurmek
# etibarlidir: hedef yoxdursa scp onu yaradir.
ssh -i $KEY $SERVER "rm -rf ${REMOTE}.new"
scp -i $KEY -r "$LOCAL\web" "${SERVER}:${REMOTE}.new"
if ($LASTEXITCODE -ne 0) { Fail "scp ugursuz oldu" }

# Atomik evezleme: kohne versiya yeni tam kocuruldukden SONRA silinir,
# beleliklen sayt kocurme muddetinde yarimciq gorunmur.
ssh -i $KEY $SERVER "rm -rf ${REMOTE}.new/tests && rm -rf ${REMOTE}.old && (test -d $REMOTE && mv $REMOTE ${REMOTE}.old || true) && mv ${REMOTE}.new $REMOTE && rm -rf ${REMOTE}.old"
if ($LASTEXITCODE -ne 0) { Fail "serverde evezleme ugursuz oldu" }

# ── 4. nginx ─────────────────────────────────────────────────────────
Write-Host "nginx yoxlanilir ve yenilenir..." -ForegroundColor Cyan
ssh -i $KEY $SERVER "nginx -t && systemctl reload nginx"
if ($LASTEXITCODE -ne 0) { Fail "nginx konfiqurasiyasi sinliqdir - reload edilmedi" }

# ── 5. Healthcheck ───────────────────────────────────────────────────
# Deploy "ugurlu" sayilmir - canli unvandan TESDIQ olunmalidir.
Write-Host "Canli unvan yoxlanilir..." -ForegroundColor Cyan
$site = ssh -i $KEY $SERVER "curl -s -o /dev/null -w '%{http_code}' https://masterai.prdostu.com/"
$api  = ssh -i $KEY $SERVER "curl -s -o /dev/null -w '%{http_code}' https://masterai.prdostu.com/health"
Write-Host "  Sayt: $site   API: $api"
if ($site -ne "200") { Fail "Sayt $site qaytardi (200 gozlenilirdi)" }
if ($api  -ne "200") { Fail "API $api qaytardi (200 gozlenilirdi)" }

Write-Host "Deploy tamamlandi." -ForegroundColor Green
