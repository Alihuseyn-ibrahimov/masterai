/* Canlı sessiyanın BAĞLANTI KƏSİLMƏSİNƏ davamlılığı.
 *
 * NİYƏ: real sinifdə bağlantı kəsilir — telefon kilidlənir, wifi düşür,
 * müəllimin noutbuku yuxuya gedir. Bu yollar indiyədək HEÇ sınanmamışdı,
 * halbuki `ReconnectingSocket` (web/assets/js/socket.js) məhz bunun üçün
 * yazılıb.
 *
 * İKİ SSENARİ:
 *   student  — tələbənin bağlantısı kəsilir və qayıdır
 *   host     — MÜƏLLİMİN bağlantısı kəsilir (daha ağır: sessiya onun
 *              konsoluna bağlı görünür)
 *
 * İŞLƏTMƏK:
 *   1. Backend (yaddaşdaxili nüsxə kifayətdir) — 8125
 *   2. .venv/bin/python -m http.server 8123 --directory web
 *   3. npm i playwright-core   (bir dəfə)
 *   4. node deploy/diagnostics/live_session_resilience.mjs <TOKEN> student
 *      node deploy/diagnostics/live_session_resilience.mjs <TOKEN> host
 *
 * 2026-09-11 NƏTİCƏLƏRİ (hər ikisi TƏMİZ):
 *
 *   student: qayıtdıqdan sonra iştirakçı TƏKRARLANMIR (host-da yenə 2
 *     nəfər), cavabı və tərəqqisi (1/4) qorunur, «Növbəti sual» işləyir,
 *     2-ci sualı cavablaya bilir, host gedişatı 2/4-ə yenilənir.
 *
 *   host: müəllim offline ikən TƏLƏBƏLƏR CAVABLAMAĞA DAVAM EDİR — dərs
 *     dayanmır. Host qayıdanda bağlantı «Bağlıdır» olur və gedişat
 *     siyahısı özü-özünə yetişir (kəsilmə müddətindəki cavabları göstərir).
 *     Yəni sessiya host-un soketinə BAĞLI DEYİL.
 */
/* playwright-core İŞLƏDİYİN QOVLUQDAN yüklənir, bu faylın yerindən YOX.
 * Səbəb: ESM `import` modulu faylın qovluğundan yuxarı axtarır, yəni
 * `masterai/`-də `node_modules` olmasa sınır. `createRequire(cwd)` ilə
 * paket `npm i playwright-core` etdiyin İSTƏNİLƏN qovluqdan tapılır -
 * repoya `node_modules` əlavə etməyə ehtiyac qalmır («build addımı
 * yoxdur» qaydası pozulmur). */
import { createRequire } from 'node:module';
const require = createRequire(`${process.cwd()}/`);
const { chromium } = require('playwright-core');

const token = process.argv[2];
const MODE = process.argv[3] === 'host' ? 'host' : 'student';
if (!token) {
  console.error('İşlətmə: node live_session_resilience.mjs <MÜƏLLİM_TOKENİ> [student|host]');
  process.exit(1);
}

const CHROME = process.env.CHROME_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const SITE = process.env.SITE_URL || 'http://127.0.0.1:8123';
const API = process.env.API_URL || 'http://127.0.0.1:8125';

const b = await chromium.launch({ executablePath: CHROME });
const errs = [];

/* `config.js` canlı ünvana baxır — yerli backend-ə yönəldirik. */
const redirect = async (ctx) => {
  await ctx.route((url) => url.pathname.endsWith('/assets/js/config.js'), async (route) => {
    const res = await route.fetch();
    const body = (await res.text())
      .replace("'https://masterai.prdostu.com'", `'${API}'`)
      .replace("'wss://masterai.prdostu.com'", `'${API.replace('http', 'ws')}'`);
    await route.fulfill({ status: 200, contentType: 'application/javascript', body });
  });
};

const hostCtx = await b.newContext({ viewport: { width: 1200, height: 900 } });
await hostCtx.addInitScript((t) => {
  try {
    localStorage.setItem('masterai.token', t);
    localStorage.setItem('masterai.user', JSON.stringify({
      id: 1, email: 'm@n.az', display_name: 'Müəllim', is_teacher: true, is_admin: false,
    }));
  } catch (e) { /* localStorage bağlı ola bilər */ }
}, token);
await redirect(hostCtx);
const host = await hostCtx.newPage();
host.on('pageerror', (e) => errs.push('host: ' + e.message));
await host.goto(`${SITE}/sessiyalar.html?questionSetId=1`, { waitUntil: 'networkidle' });
await host.waitForTimeout(1500);
const pin = await host.$eval('#pinValue', (e) => e.textContent);
console.log('PIN:', pin, '| ssenari:', MODE);

const join = async (ad) => {
  const ctx = await b.newContext({ viewport: { width: 400, height: 850 } });
  await redirect(ctx);
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errs.push(`${ad}: ${e.message}`));
  await p.goto(`${SITE}/qosul.html`, { waitUntil: 'networkidle' });
  await p.fill('#pin', pin);
  await p.fill('#displayName', ad);
  await p.click('#joinForm button[type=submit]');
  return { ctx, p, ad };
};
const kesilen = await join('Kəsilən');
const sabit = await join('Sabit');
await host.waitForTimeout(2000);
console.log('qoşulan     :', await host.$eval('#startHint', (e) => e.textContent));

await host.click('#startBtn');
await host.waitForTimeout(1500);
for (const s of [kesilen, sabit]) await s.p.click('#options button:nth-child(2)').catch(() => {});
await host.waitForTimeout(900);

const droppedCtx = MODE === 'host' ? hostCtx : kesilen.ctx;
await droppedCtx.setOffline(true);
console.log(`>>> ${MODE === 'host' ? 'MÜƏLLİM' : 'TƏLƏBƏ'} offline`);
await host.waitForTimeout(3000);

if (MODE === 'host') {
  // Müəllim yoxdur — dərs davam edirmi?
  for (const s of [kesilen, sabit]) {
    await s.p.click('#nextBtn').catch(() => {});
    await s.p.waitForTimeout(600);
    await s.p.click('#options button:nth-child(2)').catch(() => {});
  }
  await kesilen.p.waitForTimeout(1200);
  console.log('host YOX ikən cavab:',
    await kesilen.p.$eval('#resultBadge', (e) => e.textContent).catch(() => 'CAVAB GETMƏDİ'));
}

await droppedCtx.setOffline(false);
console.log('>>> online qayıtdı');
await host.waitForTimeout(6000);

console.log('host bağlantısı :', await host.$eval('#connStatus', (e) => e.textContent));
console.log('iştirakçılar    :',
  await host.$$eval('#participants .row span', (els) => els.map((e) => e.textContent)));

// Qayıtdıqdan sonra DAVAM edə bilirmi?
await kesilen.p.click('#nextBtn').catch(() => {});
await kesilen.p.waitForTimeout(1500);
console.log('növbəti sual    :',
  await kesilen.p.$eval('#questionCounter', (e) => e.textContent).catch(() => 'AÇILMADI'));
await kesilen.p.click('#options button:nth-child(2)').catch(() => {});
await kesilen.p.waitForTimeout(1500);
console.log('cavab nəticəsi  :',
  await kesilen.p.$eval('#resultBadge', (e) => e.textContent).catch(() => 'CAVAB GETMƏDİ'));
await host.waitForTimeout(1500);
console.log('yekun gedişat   :',
  await host.$$eval('#participants .row span', (els) => els.map((e) => e.textContent)));
console.log('JS xətaları     :', errs.length ? errs.slice(0, 4) : 'yoxdur');

await b.close();
