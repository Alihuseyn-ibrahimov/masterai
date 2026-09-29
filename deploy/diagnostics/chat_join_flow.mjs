/* Çatdan qoşulma axınının UC-UCA BRAUZER yoxlaması.
 *
 * NİYƏ AYRICA SKRIPT: yük və davamlılıq skriptləri hesab qurulmasını
 * API ilə edir (orada yoxlanılan şey sessiyadır). Burada isə yoxlanılan
 * məhz İNSAN AXINIDIR: tələbə kodu ƏL İLƏ yazır, müəllim təsdiq
 * düyməsinə BASIR, tələbə çatda sessiyanı GÖRÜR və qoşulur.
 *
 * Bu axın Faza 2-3-də yazıldı və indiyə qədər yalnız mock məlumatla
 * render edilmişdi - real backend-ə qarşı brauzerdən heç vaxt
 * keçirilməmişdi.
 *
 * İŞLƏTMƏK:
 *   node deploy/diagnostics/chat_join_flow.mjs <MÜƏLLİM_TOKENİ> [bankId]
 */

import { createRequire } from 'node:module';
const require = createRequire(`${process.cwd()}/`);
const { chromium } = require('playwright-core');

const token = process.argv[2];
const questionSetId = Number(process.argv[3] || 1);
const API = process.env.API_URL || 'http://127.0.0.1:8125';
// Qeydiyyat qapalıdır (2026-09-29): tələbələr bu kursa yazılır. Kodu
// sahib panelindən və ya `license_seed.py` çıxışından götür.
const COURSE_CODE = process.env.COURSE_CODE || '';
if (!COURSE_CODE) { console.error('COURSE_CODE mühit dəyişəni tələb olunur (kurs kodu)'); process.exit(1); }
const SITE = process.env.SITE_URL || 'http://127.0.0.1:8123';
if (!token) { console.error('İşlətmə: node chat_join_flow.mjs <token> [bankId]'); process.exit(1); }

const api = async (path, { method = 'GET', body, bearer = token } = {}) => {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}: ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : null;
};

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const errs = [];
const problems = [];
const check = (ok, mesaj) => { console.log(`  ${ok ? '✓' : '✗'} ${mesaj}`); if (!ok) problems.push(mesaj); };

const redirect = async (ctx) => {
  await ctx.route((url) => url.pathname.endsWith('/assets/js/config.js'), async (route) => {
    const res = await route.fetch();
    const body = (await res.text())
      .replace("'https://masterai.prdostu.com'", `'${API}'`)
      .replace("'wss://masterai.prdostu.com'", `'${API.replace('http', 'ws')}'`);
    await route.fulfill({ status: 200, contentType: 'application/javascript', body });
  });
};
const openAs = async (auth, viewport) => {
  const ctx = await b.newContext({ viewport });
  await ctx.addInitScript(([t, u]) => {
    try {
      localStorage.setItem('masterai.token', t);
      localStorage.setItem('masterai.user', JSON.stringify(u));
    } catch (e) {}
  }, [auth.token, auth.user]);
  await redirect(ctx);
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 80)); });
  return p;
};

const stamp = Date.now();
const student = await api('/auth/register', {
  method: 'POST', bearer: null,
  body: { email: `axin${stamp}@e2e.az`, password: 'Parol1234', display_name: 'Nərmin', course_code: COURSE_CODE },
});
const teacher = { token, user: { id: 1, email: 'm@n.az', display_name: 'Müəllim', is_teacher: true, is_admin: false } };

/* ---- 1. Müəllim çat yaradır (BRAUZERDƏN) ---- */
console.log('\n1. Müəllim çat yaradır');
const chatName = `Sinif ${stamp}`;
const tPage = await openAs(teacher, { width: 1280, height: 900 });
await tPage.goto(`${SITE}/chatlar.html`, { waitUntil: 'networkidle' });
await tPage.fill('#chatName', chatName);
await tPage.click('#createBtn');
await tPage.waitForTimeout(1500);

/* Kodu MƏHZ bu çatın kartından oxuyuruq. İlk versiyamda sadəcə
   `.invite-code` yazmışdım və skript müəllimin ƏVVƏLKİ çatının kodunu
   götürürdü - tələbə səhv çata qoşulurdu və axının qalan hissəsi
   yanlış yerdən sınırdı. Bu, skriptin səhvi idi, tətbiqin yox. */
const cardOf = (name) => tPage.locator('.card').filter({ has: tPage.locator(`h4:text-is("${name}")`) });
const kod = await cardOf(chatName).locator('.invite-code').first().textContent().catch(() => null);
check(Boolean(kod && kod.includes('-')), `dəvət kodu göstərilir: ${kod}`);

/* ---- 2. Tələbə kodu ƏL İLƏ yazır ---- */
console.log('\n2. Tələbə kodu yazır (mobil, 390px)');
const sPage = await openAs(student, { width: 390, height: 844 });
await sPage.goto(`${SITE}/chatlar.html`, { waitUntil: 'networkidle' });
await sPage.fill('#inviteCode', kod.toLowerCase());  // kiçik hərflə - səhv sayılmamalıdır
await sPage.click('#joinBtn');
await sPage.waitForTimeout(1500);
const okText = await sPage.$eval('#joinOk', (e) => (e.hidden ? '' : e.textContent)).catch(() => '');
check(okText.includes('göndərildi'), `istək göndərildi mesajı: «${okText.trim().slice(0, 60)}»`);
const chatsAfterRequest = await sPage.$$eval('.card h4', (els) => els.map((e) => e.textContent));
check(!chatsAfterRequest.includes(`Sinif ${stamp}`), 'istək ÜZVLÜK yaratmır (çat hələ siyahıda yoxdur)');
const overflow = await sPage.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth);
check(overflow === 0, `390px-də üfüqi sürüşmə: ${overflow}px`);

/* ---- 3. Müəllim təsdiq düyməsinə BASIR ---- */
console.log('\n3. Müəllim təsdiqləyir');
await tPage.reload({ waitUntil: 'networkidle' });
await tPage.waitForTimeout(1500);
const card = cardOf(chatName);
const pending = await card.locator('.request-row span').allTextContents();
check(pending.includes('Nərmin'), `gözləyən istəkdə ad görünür: ${JSON.stringify(pending)}`);
await card.locator('.request-row button').first().click();   // «Təsdiqlə»
await tPage.waitForTimeout(1800);
const stillPending = await cardOf(chatName).locator('.request-row span').allTextContents();
check(stillPending.length === 0, `təsdiqdən sonra gözləyən istək qalmır (${stillPending.length})`);

/* ---- 4. Tələbə artıq üzvdür ---- */
console.log('\n4. Tələbə çatı görür');
await sPage.reload({ waitUntil: 'networkidle' });
await sPage.waitForTimeout(1200);
const myChats = await sPage.$$eval('.card h4', (els) => els.map((e) => e.textContent));
check(myChats.includes(chatName), `çat siyahıda: ${JSON.stringify(myChats.slice(0, 3))}`);
const studentSeesCode = await sPage.$$eval('.invite-code', (els) => els.filter((e) => e.textContent.trim()).length);
check(studentSeesCode === 0, 'ÜZVƏ dəvət kodu göstərilmir (yalnız yaradana)');

/* ---- 5. Müəllim çatdan sessiya başladır ---- */
console.log('\n5. Sessiya çatdan başlayır');
const chats = await api('/chats');
const chat = chats.find((c) => c.name === chatName);
await tPage.goto(`${SITE}/sessiyalar.html?questionSetId=${questionSetId}&chatId=${chat.id}`,
                 { waitUntil: 'networkidle' });
await tPage.waitForTimeout(2000);
const liveCard = await api(`/chats/${chat.id}/live-session`);
check(Boolean(liveCard), `sessiya yarandı: ${liveCard && liveCard.session_id}`);

/* ---- 6. Tələbə çatda sessiyanı GÖRÜR və qoşulur ---- */
console.log('\n6. Tələbə çatda sessiyanı görür');
await sPage.goto(`${SITE}/chat.html?id=${chat.id}`, { waitUntil: 'networkidle' });
await sPage.waitForTimeout(1500);
const cardHidden = await sPage.$eval('#liveCard', (e) => e.hidden);
check(cardHidden === false, 'sessiya kartı görünür');
const joinLabel = await sPage.$eval('#liveJoin', (e) => e.textContent);
const joinHref = await sPage.$eval('#liveJoin', (e) => e.getAttribute('href'));
check(joinLabel.trim() === 'Qoşul', `tələbə düyməsi: «${joinLabel.trim()}»`);
check(joinHref.includes(`sessiya.html?id=${liveCard.session_id}`), `düymə ünvanı: ${joinHref}`);

await sPage.click('#liveJoin');
await sPage.waitForTimeout(2000);
const waiting = await sPage.$eval('#waitCard', (e) => !e.hidden).catch(() => false);
check(waiting, 'tələbə gözləmə ekranındadır (PIN və ad YAZMADAN)');

/* ---- 7. Sessiya işləyir ---- */
console.log('\n7. Sessiya gedir');
await tPage.click('#startBtn');
await tPage.waitForTimeout(2000);
const counter = await sPage.$eval('#questionCounter', (e) => e.textContent).catch(() => 'YOXDUR');
check(counter.startsWith('Sual 1/'), `tələbəyə sual gəldi: ${counter}`);
await sPage.click('#options button:nth-child(1)');  // A düzgündür
await sPage.waitForTimeout(1200);
const badge = await sPage.$eval('#resultBadge', (e) => e.textContent).catch(() => 'YOXDUR');
check(badge === 'Düzgün', `cavab nəticəsi: ${badge}`);

/* ---- 8. Lövhə ---- */
console.log('\n8. Sinif lövhəsi');
await sPage.goto(`${SITE}/chat.html?id=${chat.id}`, { waitUntil: 'networkidle' });
await sPage.waitForTimeout(1200);
await sPage.click('#boardBox summary');
await sPage.waitForTimeout(1500);
const rows = await sPage.$$eval('.board-row', (els) => els.map((e) => e.textContent.trim()));
check(rows.length > 0, `lövhədə sətir var: ${JSON.stringify(rows)}`);
check(rows.some((r) => r.includes('Canlı sessiya 1')), 'canlı sessiya xalı lövhədə görünür');
check(!rows.some((r) => r.includes('Müəllim')), 'müəllim lövhədə YOXDUR');

console.log('\nJS xətaları:', errs.length ? errs.slice(0, 5) : 'yoxdur');
console.log(problems.length ? `\nPROBLEMLƏR (${problems.length}):\n  ${problems.join('\n  ')}`
                            : '\nPROBLEM YOXDUR ✓');
await sPage.screenshot({ path: 'axin-telebe.png', fullPage: true });
await b.close();
process.exit(problems.length ? 1 : 0);
