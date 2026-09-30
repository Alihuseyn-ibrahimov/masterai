/* İngilis dili profilinin UC-UCA BRAUZER yoxlaması (spec 2026-09-29 §5).
 *
 * LLM-siz: banklar `license_seed.py english` ilə birbaşa yazılır. Yoxlanan
 * generasiya deyil, profilin EKRANDA necə göründüyüdür:
 *   - ingilis müəllimi «Sual növü» seçimini görür, fənn «Xarici dil»dir;
 *     imtahan müəllimi görmür
 *   - canlı sessiya seçicisində reading bankı YOXDUR
 *   - tələbə ev tapşırığında mətni sualın üstündə görür
 *
 * İŞLƏTMƏK: SEED=$(python deploy/diagnostics/license_seed.py english)
 *   node deploy/diagnostics/english_profile_flow.mjs "$SEED" [ekran-şəkli-qovluğu]
 */

import { createRequire } from 'node:module';
const require = createRequire(`${process.cwd()}/`);
const { chromium } = require('playwright-core');

const seed = JSON.parse(process.argv[2] || '{}');
const SHOTS = process.argv[3] || '';
if (!seed.teacher) { console.error('İşlətmə: node english_profile_flow.mjs "<seed JSON>"'); process.exit(1); }
const API = process.env.API_URL || 'http://127.0.0.1:8125';
const SITE = process.env.SITE_URL || 'http://127.0.0.1:8123';

const problems = [];
const errs = [];
const check = (ok, mesaj) => { console.log(`  ${ok ? 'OK ' : 'XƏTA'} ${mesaj}`); if (!ok) problems.push(mesaj); };
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });

async function loggedIn(email) {
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
  await page.goto(`${SITE}/giris.html`);
  await page.fill('#email', email);
  await page.fill('#password', seed.password);
  await page.click('#submitBtn');
  await page.waitForFunction(() => !location.pathname.endsWith('giris.html'), null, { timeout: 8000 });
  return page;
}

console.log('1. Müəllim konsolu');
const teacher = await loggedIn(seed.teacher);
await teacher.goto(`${SITE}/muellim.html`);
await teacher.locator('#bankKindField:not([hidden])').waitFor({ timeout: 5000 }).catch(() => {});
check(await teacher.locator('#bankKindField').isVisible(), 'ingilis müəllimi «Sual növü» seçimini görür');
check(await teacher.locator('#subject').inputValue() === 'xarici_dil', 'fənn «Xarici dil» seçilib');
const readingCard = teacher.locator('.bank', { hasText: 'Unit 1 reading' });
await readingCard.waitFor({ timeout: 5000 });
check((await readingCard.textContent()).includes('yalnız ev tapşırığı'), 'reading bankı kartında qeyd var');

const exam = await loggedIn(seed.exam_teacher);
await exam.goto(`${SITE}/muellim.html`);
await exam.waitForTimeout(1200);
check(await exam.locator('#bankKindField').isHidden(), 'imtahan müəllimi seçimi görmür');

console.log('2. Canlı sessiya seçicisi');
await teacher.goto(`${SITE}/sessiyalar.html?chatId=${seed.chat_id}`);
await teacher.waitForTimeout(1500);
await teacher.locator("#setList .bank").first().waitFor({ timeout: 5000 }).catch(() => {});
const listText = await teacher.locator("#setList").textContent();
check(listText.includes('Unit 1 grammar'), 'adi bank seçicidədir');
check(!listText.includes('Unit 1 reading'), 'reading bankı seçicidə YOXDUR');

console.log('3. Tələbə ev tapşırığı');
const student = await loggedIn(seed.student);
await student.goto(`${SITE}/tapsiriq.html?id=${seed.assignment_id}`);
await student.locator('#questionCard:not([hidden])').waitFor({ timeout: 8000 }).catch(() => {});
check(await student.locator('#passageCard').isVisible(), 'mətn bloku görünür');
const passage = await student.locator('#passageText').textContent();
check(passage.startsWith(seed.passage_start), `mətn: ${JSON.stringify(passage.slice(0, 40))}`);
const boxBottom = await student.locator('#passageCard').evaluate((n) => n.getBoundingClientRect().bottom);
const questionTop = await student.locator('#questionText').evaluate((n) => n.getBoundingClientRect().top);
check(boxBottom <= questionTop, 'mətn sualın ÜSTÜNDƏDİR');
check(await student.locator('#questionText').textContent() === 'Why does Tom like English?', 'sual ingiliscədir');
if (SHOTS) await student.screenshot({ path: `${SHOTS}/reading-mobil.png`, fullPage: true });
await student.locator('#options button, #options .option').first().click();
await student.locator('#feedbackCard:not([hidden])').waitFor({ timeout: 5000 });
check(await student.locator('#passageCard').isVisible(), 'cavabdan sonra da mətn görünür');
check((await student.locator('#explanationText').textContent()).includes('Mətndə'), 'izah azərbaycancadır');
const sw = await student.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
check(sw === 0, `telefonda üfüqi sürüşmə yoxdur (${sw}px)`);

check(errs.length === 0, `JS xətası yoxdur ${errs.length ? JSON.stringify(errs) : ''}`);
await browser.close();
console.log(problems.length ? `\n${problems.length} PROBLEM` : '\nHamısı təmiz');
process.exit(problems.length ? 1 : 0);
