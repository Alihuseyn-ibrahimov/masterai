/* Qapalı qeydiyyatın UC-UCA BRAUZER yoxlaması (spec 2026-09-29 §4.1).
 *
 * Forma ÖZÜ doldurulur: kurs kodu (kiçik hərf + defislə), səhv kod,
 * dolu kurs, müəllim dəvət linki və təkrar istifadə olunmuş dəvət.
 *
 * İŞLƏTMƏK (lokal, boş müvəqqəti bazalarla - produksiyada YOX):
 *   SEED=$(python deploy/diagnostics/license_seed.py registration)
 *   uvicorn server.app:app --port 8125 &  +  http.server 8123 --directory web
 *   node deploy/diagnostics/registration_flow.mjs "$SEED"
 */

import { createRequire } from 'node:module';
const require = createRequire(`${process.cwd()}/`);
const { chromium } = require('playwright-core');

const seed = JSON.parse(process.argv[2] || '{}');
if (!seed.join_code) { console.error('İşlətmə: node registration_flow.mjs "<seed JSON>"'); process.exit(1); }
const API = process.env.API_URL || 'http://127.0.0.1:8125';
const SITE = process.env.SITE_URL || 'http://127.0.0.1:8123';

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

async function fill(page, { email, code, query = '' }) {
  await page.goto(`${SITE}/qeydiyyat.html${query}`);
  await page.fill('#displayName', 'E2E');
  await page.fill('#email', email);
  await page.fill('#password', seed.password);
  if (code !== undefined) await page.fill('#courseCode', code);
  await page.click('#submitBtn');
}

/* Ya yönləndirmə, ya da xəta qutusu - hansı birinci gəlsə. `waitForURL`
 * işlədilmir (bax license_gate_flow.mjs: öz-özünə yönləndirmə onu kəsir). */
async function outcome(page) {
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    const path = new URL(page.url()).pathname;
    if (!path.endsWith('/qeydiyyat.html')) return { path };
    if (await page.locator('#errorBox').isVisible()) {
      return { path, error: await page.locator('#errorBox').textContent() };
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  return { path: new URL(page.url()).pathname };
}

const stamp = Date.now();
const code = seed.join_code;
const messy = `${code.slice(0, 3).toLowerCase()}-${code.slice(3).toLowerCase()}`;

console.log('1. Səhv kod');
let p = await newPage();
await fill(p, { email: `s0${stamp}@e2e.az`, code: 'ZZZ-ZZZ' });
let r = await outcome(p);
check(Boolean(r.error && r.error.includes('Kurs kodu tapılmadı')), `səhv kod: ${JSON.stringify(r)}`);

console.log('2. Doğru kod (kiçik hərf + defis)');
p = await newPage();
await fill(p, { email: `s1${stamp}@e2e.az`, code: messy });
r = await outcome(p);
check(r.path.endsWith('/chatlar.html'), `tələbə qeydiyyatı: ${JSON.stringify(r)}`);

console.log('3. Kurs doludur (1 yer)');
p = await newPage();
await fill(p, { email: `s2${stamp}@e2e.az`, code });
r = await outcome(p);
check(Boolean(r.error && r.error.includes('boş yer qalmayıb')), `dolu kurs: ${JSON.stringify(r)}`);

console.log('4. Müəllim dəvət linki');
const query = `?invite=${encodeURIComponent(seed.invite)}`;
p = await newPage();
await p.goto(`${SITE}/qeydiyyat.html${query}`);
check(await p.locator('#courseCodeField').isHidden(), 'dəvətlə kurs kodu sahəsi gizlidir');
check(await p.locator('#inviteNote').isVisible(), 'dəvət qeydi görünür');
await fill(p, { email: `t1${stamp}@e2e.az`, query });
r = await outcome(p);
check(r.path.endsWith('/muellim.html'), `müəllim qeydiyyatı: ${JSON.stringify(r)}`);

console.log('5. Eyni dəvət ikinci dəfə');
p = await newPage();
await fill(p, { email: `t2${stamp}@e2e.az`, query });
r = await outcome(p);
check(Boolean(r.error && r.error.includes('Dəvət linki etibarsızdır')), `təkrar dəvət: ${JSON.stringify(r)}`);

check(errs.length === 0, `JS xətası yoxdur ${errs.length ? JSON.stringify(errs) : ''}`);
await browser.close();
console.log(problems.length ? `\n${problems.length} PROBLEM` : '\nHamısı təmiz');
process.exit(problems.length ? 1 : 0);
