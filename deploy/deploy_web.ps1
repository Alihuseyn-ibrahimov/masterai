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

# ── 1. Python interpretatorunu tap ───────────────────────────────────
# venv layihe kokunde de, masterai/ daxilinde de ola biler (real
# muhitde masterai/.venv yox idi). Kor-korane bir yol yazmaq eveztne
# hamisi yoxlanilir; tapilmasa aydin xeta verilir.
$REPO_ROOT = Split-Path -Parent $LOCAL
$PY_CANDIDATES = @(
    "$LOCAL\.venv\Scripts\python.exe",
    "$REPO_ROOT\.venv\Scripts\python.exe",
    "$LOCAL\venv\Scripts\python.exe",
    "$REPO_ROOT\venv\Scripts\python.exe"
)
$PYTHON = $null
foreach ($candidate in $PY_CANDIDATES) {
    if (Test-Path $candidate) { $PYTHON = $candidate; break }
}
if (-not $PYTHON) {
    # Son care: sistemdeki `py` launcher (bax repo kokundeki CLAUDE.md —
    # bu masinda `python` YOXDUR, yalniz `py` var).
    if (Get-Command py -ErrorAction SilentlyContinue) { $PYTHON = "py" }
}
if (-not $PYTHON) {
    Fail ("Python tapilmadi. Yoxlanilan yerler:`n  " + ($PY_CANDIDATES -join "`n  "))
}
Write-Host "Python: $PYTHON" -ForegroundColor DarkGray

# ── 2. Test qapısı ───────────────────────────────────────────────────
# YALNIZ veb testleri isledilir — bu skript statik HTML/CSS/JS kocurur,
# backend-e TOXUNMUR. Hemin dord fayl yalniz standart kitabxana + pytest
# teleb edir (metn analizi), yeni Windows-da agir backend muhiti
# (langchain, selenium, pytesseract...) qurmaga ehtiyac yoxdur.
#
# Backend test desti (750 test) ayrica, her commit-de sandbox-da ve
# VPS-de islenir — bura daxil edilmemesi onun atlandigi anlamina gelmir.
$WEB_TESTS = @(
    "tests\test_web_pages.py",
    "tests\test_web_design_system.py",
    "tests\test_web_client_contract.py",
    "tests\test_nginx_routes.py"
)
Write-Host "Veb testleri isledilir..." -ForegroundColor Cyan
Push-Location $LOCAL
& $PYTHON -m pytest -q @WEB_TESTS
$testExit = $LASTEXITCODE
Pop-Location
if ($testExit -ne 0) {
    Fail ("Veb testleri ugursuz oldu - deploy DAYANDIRILDI.`n" +
          "pytest tapilmadisa: & '$PYTHON' -m pip install pytest")
}

if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "JavaScript testleri isledilir..." -ForegroundColor Cyan
    & node --test (Get-ChildItem "$LOCAL\web\tests\*.test.js" | ForEach-Object { $_.FullName })
    if ($LASTEXITCODE -ne 0) { Fail "JS testleri ugursuz oldu - deploy DAYANDIRILDI" }
} else {
    Write-Host "Node tapilmadi - JS testleri atlandi." -ForegroundColor Yellow
}

# ── 3. Disk yoxlamasi ────────────────────────────────────────────────
# Bu VPS-de disk dolmasi eweller masterai-ni COKDURUB ve masternr1
# (aktiv pilot) daxil dord servisi riske atib. Kocurmeden EVVEL
# yoxlamaq mecburidir (bax masterai/CLAUDE.md, "Ders: real deploy telelerи").
Write-Host "Serverin disk veziyyeti yoxlanilir..." -ForegroundColor Cyan
$usage = ssh -i $KEY $SERVER "df --output=pcent / | tail -1 | tr -dc '0-9'"
Write-Host "  Disk istifadesi: $usage%"
if ([int]$usage -ge 98) { Fail "Disk $usage% doludur - kocurme servisleri riske atar" }

# ── 4. Kocurme ───────────────────────────────────────────────────────
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

# ICAZELER: scp fayllari root adindan yazir, nginx ise www-data kimi
# isleyir. Qovluga girmek icazesi olmasa nginx 403 qaytarir (real
# deploy-da bas verdi). `a+rX` — fayllara oxuma, YALNIZ qovluqlara
# icra icazesi (boyuk X bunu edir; fayllara icra verilmir).
ssh -i $KEY $SERVER "chmod -R a+rX $REMOTE"
if ($LASTEXITCODE -ne 0) { Fail "icazeler teyin edilmedi" }

# ── 5. nginx ─────────────────────────────────────────────────────────
Write-Host "nginx yoxlanilir ve yenilenir..." -ForegroundColor Cyan
ssh -i $KEY $SERVER "nginx -t && systemctl reload nginx"
if ($LASTEXITCODE -ne 0) { Fail "nginx konfiqurasiyasi sinliqdir - reload edilmedi" }

# ── 6. Healthcheck ───────────────────────────────────────────────────
# Deploy "ugurlu" sayilmir - canli unvandan TESDIQ olunmalidir.
Write-Host "Canli unvan yoxlanilir..." -ForegroundColor Cyan
$site = ssh -i $KEY $SERVER "curl -s -o /dev/null -w '%{http_code}' https://masterai.prdostu.com/"
$api  = ssh -i $KEY $SERVER "curl -s -o /dev/null -w '%{http_code}' https://masterai.prdostu.com/health"
Write-Host "  Sayt: $site   API: $api"
if ($site -ne "200") { Fail "Sayt $site qaytardi (200 gozlenilirdi)" }
if ($api  -ne "200") { Fail "API $api qaytardi (200 gozlenilirdi)" }

# SRIFT YOXLAMASI. Sriftler artiq oz serverimizdedir; bu yol nginx-de
# hec vaxt sinanmayib. Fayl gelmese ve ya MIME sehv olsa, sayt SINMIR —
# sadece Azerbaycan herfleri fallback sriftle cixir. Yeni gozle
# baxanda "islediyi" gorunur. Ona gore MENBEDEN yoxlanilir.
$FONT_URL = "https://masterai.prdostu.com/assets/fonts/source-serif-4-latin-ext.woff2"
$fontCode = ssh -i $KEY $SERVER "curl -s -o /dev/null -w '%{http_code}' $FONT_URL"
$fontType = ssh -i $KEY $SERVER "curl -s -o /dev/null -w '%{content_type}' $FONT_URL"
Write-Host "  Srift: $fontCode ($fontType)"
if ($fontCode -ne "200") { Fail "Srift fayli $fontCode qaytardi - basliqlar fallback sriftle cixacaq" }
if ($fontType -notmatch "font|woff") {
    Fail "Srift MIME tipi sehvdir: '$fontType' (font/woff2 gozlenilirdi). nginx mime.types yoxlanmalidir."
}

Write-Host "Deploy tamamlandi." -ForegroundColor Green
