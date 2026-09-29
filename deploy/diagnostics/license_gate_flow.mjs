/* Lisenziya qapısının UC-UCA BRAUZER yoxlaması (spec 2026-09-29 §2).
 *
 * pytest serverin 402/4402 qaytardığını sübut edir; bu skript isə
 * İSTİFADƏÇİNİN NƏ GÖRDÜYÜNÜ: giriş formu, banner, bağlı səhifə,
 * söhbət ortasında bağlanma, ödənişdən sonra «Yenidən yoxla».
 *
 * İŞLƏTMƏK (lokal, boş müvəqqəti bazalarla - produksiyada YOX):
 *   export USERS_DB_PATH=/tmp/x/users.db CHATS_DB_PATH=/tmp/x/chats.db ...
 *   SEED=$(python deploy/diagnostics/license_seed.py seed)
 *   uvicorn server.app:app --port 8125 &
 *   python -m http.server 8123 --directory web &
 *   node deploy/diagnostics/license_gate_flow.mjs "$SEED"
 * Problem tapsa sıfırdan fərqli kodla çıxır.
 */

import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
const require = createRequire(`${process.cwd()}/`);
const { chromium } = require('playwright-core');

const seed = JSON.parse(process.argv[2] || '{}');
if (!seed.course_id) { console.error('İşlətmə: node license_gate_flow.mjs "<seed JSON>"'); process.exit(1); }
const API = process.env.API_URL || 'http://127.0.0.1:8125';
const SITE = process.env.SITE_URL || 'http://127.0.0.1:8123';
const PYTHON = process.env.PYTHON || 'python';

const setStatus = (status) =>
  execFileSync(PYTHON, ['deploy/diagnostics/license_seed.py', 'status', String(seed.course_id), status]);

const problems = [];
const errs = [];
const check = (ok, mesaj) => { console.log(`  ${ok ? 'OK ' : 'XƏTA'} ${mesaj}`); if (!ok) problems.push(mesaj); };

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });

async function newPage() {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await ctx.route((url) => url.pathname.endsWith('/assets/js/config.js'), async (route) => {
    const res = await route.fetch();
    const body = (await res.text())
      .replace("'https://masterai.prdostu.com'", `'${API}'`)
      .replace("'wss://masterai.prdostu.com'", `'${API.replace('http', 'ws')}'`);
    await route.fulfill({ status: 200, contentType: 'application/javascript', body });
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errs.push(e.message));
  return page;
}

async function loginVia(page, email) {
  await page.goto(`${SITE}/giris.html`);
  await page.fill('#email', email);
  await page.fill('#password', seed.password);
  await page.click('#submitBtn');
  await page.waitForURL((u) => !u.pathname.endsWith('/giris.html'), { timeout: 8000 });
}

/* `waitForURL` İŞLƏDİLMİR: səhifə 402 alıb öz-özünə `location.replace`
 * edəndə Playwright-ın gözlədiyi naviqasiya kəsilir və o, DƏRHAL xəta
 * atır - yönləndirmə hələ bitməmiş URL oxunurdu (4 qaçışdan 2-si yalançı
 * «XƏTA» verdi; jurnal yönləndirmənin 62 ms sonra baş verdiyini göstərdi). */
async function waitForPath(page, suffix, timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (new URL(page.url()).pathname.endsWith(suffix)) return;
    await new Promise((r) => setTimeout(r, 100));
  }
}

const bannerText = (page) =>
  page.locator('.app-shell > .notice--warning').first().textContent({ timeout: 4000 }).catch(() => null);

console.log('1. Açıq kurs, 3 gün qalıb');
const teacher = await newPage();
await loginVia(teacher, seed.teacher);
check(teacher.url().endsWith('/muellim.html'), `müəllim girişdən sonra: ${new URL(teacher.url()).pathname}`);
const tBanner = await bannerText(teacher);
check(Boolean(tBanner && tBanner.includes('3 gün')), `müəllim banneri: ${JSON.stringify(tBanner)}`);

const student = await newPage();
await loginVia(student, seed.student);
await student.waitForTimeout(1500);
check((await student.locator('.app-shell > .notice--warning').count()) === 0, 'tələbəyə banner göstərilmir');

console.log('2. Söhbət ortasında kurs dayandırılır');
await student.goto(`${SITE}/chat.html?id=${seed.chat_id}`);
await student.waitForTimeout(1500);
setStatus('suspended');
await student.fill('#messageInput', 'salam');
await student.click('#sendBtn');
await waitForPath(student, '/bagli.html');
check(student.url().endsWith('/bagli.html'), `tələbə WS 4402-dən sonra: ${new URL(student.url()).pathname}`);
const heading = await student.locator('h1').textContent().catch(() => '');
check(heading.includes('abunəsi bitib'), `bağlı səhifə başlığı: ${JSON.stringify(heading)}`);

console.log('3. Bağlı kursda səhifə yeniləmə və yeni giriş');
await teacher.goto(`${SITE}/chatlar.html`);
await waitForPath(teacher, '/bagli.html');
check(teacher.url().endsWith('/bagli.html'), `müəllim HTTP 402-dən sonra: ${new URL(teacher.url()).pathname}`);

const fresh = await newPage();
await fresh.goto(`${SITE}/giris.html`);
await fresh.fill('#email', seed.student);
await fresh.fill('#password', seed.password);
await fresh.click('#submitBtn');
await waitForPath(fresh, '/bagli.html');
check(fresh.url().endsWith('/bagli.html'), `bağlı kursa giriş cəhdi: ${new URL(fresh.url()).pathname}`);

console.log('4. «Yenidən yoxla» - ödəniş olmadan, sonra ödənişdən sonra');
await student.click('#retryBtn');
await student.waitForTimeout(1000);
const status = await student.locator('#statusBox').textContent();
check(student.url().endsWith('/bagli.html') && status.includes('yenilənməyib'), `ödənişsiz: ${JSON.stringify(status)}`);
setStatus('trial');
await student.click('#retryBtn');
await waitForPath(student, '/chatlar.html');
check(student.url().endsWith('/chatlar.html'), `bərpadan sonra: ${new URL(student.url()).pathname}`);

check(errs.length === 0, `JS xətası yoxdur ${errs.length ? JSON.stringify(errs) : ''}`);
await browser.close();
console.log(problems.length ? `\n${problems.length} PROBLEM` : '\nHamısı təmiz');
process.exit(problems.length ? 1 : 0);
