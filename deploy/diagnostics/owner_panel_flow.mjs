/* Sahib panelinin UC-UCA BRAUZER yoxlaması (spec 2026-09-29 §3).
 *
 * Real kliklərlə: profil → panel → kurs yarat → ödənildi → dayandır →
 * bərpa et → müəllim dəvəti → dəvət linki ilə qeydiyyat. Sahib OLMAYAN
 * admin isə paneli görməməlidir. Nəticə ekrandan yox, həm də API-dən
 * (server nə saxlayıb) yoxlanılır.
 *
 * İŞLƏTMƏK (lokal, boş müvəqqəti bazalarla - produksiyada YOX):
 *   SEED=$(python deploy/diagnostics/license_seed.py owner)
 *   uvicorn server.app:app --port 8125 &  +  http.server 8123 --directory web
 *   node deploy/diagnostics/owner_panel_flow.mjs "$SEED" [ekran-şəkli-qovluğu]
 */

import { createRequire } from 'node:module';
const require = createRequire(`${process.cwd()}/`);
const { chromium } = require('playwright-core');

const seed = JSON.parse(process.argv[2] || '{}');
const SHOTS = process.argv[3] || '';
if (!seed.owner) { console.error('İşlətmə: node owner_panel_flow.mjs "<seed JSON>"'); process.exit(1); }
const API = process.env.API_URL || 'http://127.0.0.1:8125';
const SITE = process.env.SITE_URL || 'http://127.0.0.1:8123';

const problems = [];
const errs = [];
const check = (ok, mesaj) => { console.log(`  ${ok ? 'OK ' : 'XƏTA'} ${mesaj}`); if (!ok) problems.push(mesaj); };
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });

async function newPage(width = 390) {
  const ctx = await browser.newContext({ viewport: { width, height: 844 } });
  await ctx.route((url) => url.pathname.endsWith('/assets/js/config.js'), async (route) => {
    const res = await route.fetch();
    const body = (await res.text())
      .replace("'https://masterai.prdostu.com'", `'${API}'`)
      .replace("'wss://masterai.prdostu.com'", `'${API.replace('http', 'ws')}'`);
    await route.fulfill({ status: 200, contentType: 'application/javascript', body });
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errs.push(e.message));
  page.on('dialog', (d) => d.accept());  // təsdiq pəncərələri (confirm)
  return page;
}

async function login(page, email) {
  await page.goto(`${SITE}/giris.html`);
  await page.fill('#email', email);
  await page.fill('#password', seed.password);
  await page.click('#submitBtn');
  await page.waitForFunction(() => !location.pathname.endsWith('giris.html'), null, { timeout: 8000 });
}

const card = (page, name) => page.locator('#courses article', { hasText: name });
const badge = (page, name) => card(page, name).locator('.badge').textContent();
const waitText = (locator, text) =>
  locator.filter({ hasText: text }).first().waitFor({ timeout: 8000 }).then(() => true).catch(() => false);

console.log('1. Profil → Sahib paneli');
const owner = await newPage();
await login(owner, seed.owner);
await owner.goto(`${SITE}/profil.html`);
check(await owner.locator('#ownerExtras').isVisible(), 'profil sahibə panel linkini göstərir');
await owner.click('#ownerExtras a');
await owner.waitForSelector('#courses article');
check(new URL(owner.url()).pathname.endsWith('/sahib.html'), 'panel açıldı');
check((await owner.locator('.bottom-nav [aria-current="page"]').textContent()).includes('Profil'), 'naviqasiyada Profil aktivdir');
check((await badge(owner, 'MasterAI')).includes('Müddətsiz'), 'kurs #1 «Müddətsiz»');

console.log('2. Kurs yarat');
const NAME = `E2E English ${Date.now() % 10000}`;
await owner.click('#createPanel summary');
await owner.fill('#courseName', NAME);
await owner.selectOption('#courseProfile', 'english');
await owner.fill('#trialDays', '30');
await owner.fill('#seatLimit', '20');
await owner.click('#createBtn');
check(await waitText(owner.locator('#okBox'), 'yaradıldı'), `uğur mesajı: ${await owner.locator('#okBox').textContent()}`);
await card(owner, NAME).waitFor();
check((await badge(owner, NAME)).includes('Sınaq'), 'yeni kurs «Sınaq»');
const text = await card(owner, NAME).textContent();
check(text.includes('30 gün qalıb') && text.includes('0 / 20'), 'kart: 30 gün, 0 / 20');

console.log('3. Ödəniş, dayandırma, bərpa');
await card(owner, NAME).getByRole('button', { name: '+1 ay ödənildi' }).click();
check(await waitText(card(owner, NAME).locator('.badge'), 'Ödənilib'), 'ödənişdən sonra «Ödənilib»');
check((await card(owner, NAME).textContent()).includes('60 gün qalıb'), 'sınaq günləri itmədi: 60 gün');
await card(owner, NAME).getByRole('button', { name: 'Dayandır' }).click();
check(await waitText(card(owner, NAME).locator('.badge'), 'Dayandırılıb'), '«Dayandırılıb»');
await card(owner, NAME).getByRole('button', { name: 'Bərpa et' }).click();
check(await waitText(card(owner, NAME).locator('.badge'), 'Ödənilib'), 'bərpadan sonra yenə «Ödənilib»');
const auditNow = await owner.locator('#auditLog').textContent();
console.log(`    [diaqnoz] bərpadan dərhal sonra jurnal: ${JSON.stringify(auditNow.slice(0, 60))}`);
/* Panel əvvəl kursları, SONRA jurnalı yeniləyir - nişan dəyişəndə jurnal
   hələ «Yüklənir» ola bilər. Son əməliyyatın görünməsini gözləyirik. */
await waitText(owner.locator('#auditLog'), 'Bərpa edildi');
const audit = await owner.locator('#auditLog').textContent();
check(['Kurs yaradıldı', 'Ödəniş', 'Dayandırıldı', 'Bərpa edildi'].every((a) => audit.includes(a)), 'jurnalda 4 əməliyyat');

console.log('3b. Limitlər forması');
await card(owner, NAME).locator('details summary', { hasText: 'Limitlər' }).click();
await card(owner, NAME).getByLabel('Tələbə limiti').fill('25');
await card(owner, NAME).getByRole('button', { name: 'Saxla' }).click();
check(await waitText(card(owner, NAME), '0 / 25'), 'limit 25-ə dəyişdi (kartda 0 / 25)');
const logNow = await owner.locator('#auditLog').textContent();
console.log(`    [diaqnoz] saxladıqdan dərhal sonra jurnal: ${JSON.stringify(logNow.slice(0, 50))}`);
// Kart əvvəl, jurnal SONRA yenilənir (sahib.html `reload`) - gözləyirik.
await waitText(owner.locator('#auditLog'), 'tələbə limiti 25');
const log = await owner.locator('#auditLog').textContent();
const bad = log.match(/.{0,40}(english|active|seat_limit).{0,20}/);
check(log.includes('tələbə limiti 25') && !bad, `jurnal insan dilindədir ${bad ? JSON.stringify(bad[0]) : ''}`);

console.log('4. Müəllim dəvəti → qeydiyyat');
await card(owner, NAME).getByRole('button', { name: 'Müəllim dəvəti' }).click();
await owner.waitForSelector('#inviteCard:not([hidden])');
const link = await owner.locator('#inviteLink').inputValue();
check(link.includes('/qeydiyyat.html?invite='), `dəvət linki: ${link.slice(0, 60)}...`);
if (SHOTS) await owner.screenshot({ path: `${SHOTS}/sahib-mobil.png`, fullPage: true });
const sw = await owner.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
check(sw === 0, `telefonda üfüqi sürüşmə yoxdur (${sw}px)`);

const teacher = await newPage();
await teacher.goto(link);
await teacher.fill('#displayName', 'Dəvətli müəllim');
await teacher.fill('#email', `dvt${Date.now()}@e2e.az`);
await teacher.fill('#password', seed.password);
await teacher.click('#submitBtn');
await teacher.waitForFunction(() => !location.pathname.endsWith('qeydiyyat.html'), null, { timeout: 8000 }).catch(() => {});
check(new URL(teacher.url()).pathname.endsWith('/muellim.html'), `dəvətli qeydiyyat: ${new URL(teacher.url()).pathname}`);

await owner.click('#refreshBtn');
await owner.waitForTimeout(800);
check((await card(owner, NAME).textContent()).includes('Müəllim1'), 'kartda müəllim sayı 1');

console.log('5. Sahib olmayan admin');
const other = await newPage();
await login(other, seed.other);
await other.goto(`${SITE}/profil.html`);
check(await other.locator('#ownerExtras').isHidden(), 'admin profilində panel linki yoxdur');
await other.goto(`${SITE}/sahib.html`);
check(await waitText(other.locator('.state__title'), 'mövcud deyil'), 'admin paneli açanda «Bu səhifə mövcud deyil»');
check(await other.locator('#createSection').isHidden(), 'yaratma forması gizlidir');
const direct = await fetch(`${API}/owner/courses`, {
  headers: { Authorization: `Bearer ${await other.evaluate(() => localStorage.getItem('masterai.token'))}` },
});
check(direct.status === 404, `API birbaşa: ${direct.status}`);

if (SHOTS) {
  const wide = await newPage(1280);
  await login(wide, seed.owner);
  await wide.goto(`${SITE}/sahib.html`);
  await wide.waitForSelector('#courses article');
  await wide.screenshot({ path: `${SHOTS}/sahib-genis.png`, fullPage: true });
}

check(errs.length === 0, `JS xətası yoxdur ${errs.length ? JSON.stringify(errs) : ''}`);
await browser.close();
console.log(problems.length ? `\n${problems.length} PROBLEM` : '\nHamısı təmiz');
process.exit(problems.length ? 1 : 0);
