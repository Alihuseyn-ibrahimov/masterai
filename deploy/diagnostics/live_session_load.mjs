/* Canlı sessiyanın ÇOXİŞTİRAKÇILI yük yoxlaması.
 *
 * NİYƏ: `CLAUDE.md` aylarla yazırdı ki, canlı sessiya "yalnız 1
 * iştirakçı ilə sınanıb" - real sinifdə 20-30 tələbə eyni anda
 * qoşulacaq və eyni anda cavablayacaq. `server/user_store.py` modul
 * qeydindəki sqlite kilid dərsi məhz bu ssenaridən gəlir.
 *
 * NƏ EDİR: N ayrı brauzer konteksti açır (hər biri ayrı localStorage və
 * ayrı WebSocket = ayrı "cihaz"), hamısını eyni PIN-lə qoşur, host
 * sessiyanı başladır, hamısı EYNİ ANDA cavablayır.
 *
 * NƏ İSBAT ETMİR: bu, bir maşındakı brauzer kontekstləridir - real
 * şəbəkə gecikməsi, mobil rabitə və ayrı-ayrı telefonlar yoxdur.
 * Server tərəfin eyni anda gələn N bağlantını və N cavabı düzgün
 * emal etdiyini göstərir, şəbəkə davranışını YOX.
 *
 * İŞLƏTMƏK:
 *   1. Backend işə sal (yaddaşdaxili nüsxə kifayətdir) - 8125
 *   2. Statik sayt: .venv/bin/python -m http.server 8123 --directory web
 *   3. npm i playwright-core   (bir dəfə)
 *   4. node deploy/diagnostics/live_session_load.mjs <MÜƏLLİM_TOKENİ> 25
 *
 * NƏTİCƏNİ MƏTNDƏN YOX, API-DƏN YOXLA (ən vacib qayda):
 *   curl -H "Authorization: Bearer <token>" .../live/sessions/<id>/report
 *   - hər sualda `total_answers` iştirakçı sayına BƏRABƏR olmalıdır
 *     (az olsa cavab İTİB);
 *   - heç bir `score` sual sayını aşmamalıdır.
 *
 * 2026-09-11 nəticəsi: 25 iştirakçı, 4 sual - 25/25 cavab hər sualda,
 * xal aralığı 0-3, həddi aşan yoxdur, server jurnalında 0 xəta
 * (`OperationalError` yoxdur).
 */

/* ÇOXİŞTİRAKÇILI canlı sessiya - CLAUDE.md-də açıq qalan boşluq.
   Real backend (8125) + real sayt (8123). N ayrı brauzer konteksti =
   N ayrı "cihaz" (ayrı localStorage, ayrı WebSocket). */
import { chromium } from 'playwright-core';

const token = process.argv[2];
const N = Number(process.argv[3] || 4);
const ADLAR = Array.from({ length: 30 }, (u, i) =>
  ['Aysel', 'Elvin', 'Nigar', 'Rəşad', 'Leyla', 'Tural', 'Günel', 'Orxan',
   'Sevinc', 'Kamran', 'Lalə', 'Fərid'][i % 12] + ' ' + (Math.floor(i / 12) + 1));

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const errs = [];

const redirect = async (ctx) => {
  await ctx.route((url) => url.pathname.endsWith('/assets/js/config.js'), async (route) => {
    const res = await route.fetch();
    const body = (await res.text())
      .replace("'https://masterai.prdostu.com'", "'http://127.0.0.1:8125'")
      .replace("'wss://masterai.prdostu.com'", "'ws://127.0.0.1:8125'");
    await route.fulfill({ status: 200, contentType: 'application/javascript', body });
  });
};
const watch = (p, who) => {
  p.on('pageerror', e => errs.push(`${who}: ${e.message}`));
  p.on('console', m => { if (m.type() === 'error') errs.push(`${who} konsol: ${m.text().slice(0, 80)}`); });
};

// ---- Host ----
const hostCtx = await b.newContext({ viewport: { width: 1280, height: 900 } });
await hostCtx.addInitScript((t) => {
  try {
    localStorage.setItem('masterai.token', t);
    localStorage.setItem('masterai.user', JSON.stringify({ id: 1, email: 'm@n.az', display_name: 'Müəllim', is_teacher: true, is_admin: false }));
  } catch (e) {}
}, token);
await redirect(hostCtx);
const host = await hostCtx.newPage();
watch(host, 'host');
await host.goto('http://127.0.0.1:8123/sessiyalar.html?questionSetId=1', { waitUntil: 'networkidle' });
await host.waitForTimeout(1500);
const pin = await host.$eval('#pinValue', e => e.textContent);
console.log(`PIN: ${pin} | host: ${await host.$eval('#connStatus', e => e.textContent)}`);

// ---- N tələbə, EYNİ ANDA qoşulur ----
const students = [];
const joinStart = Date.now();
await Promise.all(Array.from({ length: N }, async (unused, i) => {
  const ctx = await b.newContext({ viewport: { width: 400, height: 850 } });
  await redirect(ctx);
  const p = await ctx.newPage();
  watch(p, ADLAR[i]);
  await p.goto('http://127.0.0.1:8123/qosul.html', { waitUntil: 'networkidle' });
  await p.fill('#pin', pin);
  await p.fill('#displayName', ADLAR[i]);
  await p.click('#joinForm button[type=submit]');
  students[i] = p;
}));
await host.waitForTimeout(3500);
console.log('qoşulma müddəti:', Date.now() - joinStart, 'ms');
console.log('host ipucu :', await host.$eval('#startHint', e => e.textContent));
console.log('iştirakçı  :', await host.$$eval('#participants .text-sm', els => els.map(e => e.textContent).filter(t => !t.includes('/'))));

// ---- Başlat ----
await host.click('#startBtn');
await host.waitForTimeout(2000);

// ---- Hamısı EYNİ ANDA cavablayır (hər sual üçün) ----
const TOTAL = 4;
for (let q = 0; q < TOTAL; q += 1) {
  await Promise.all(students.map(async (p, i) => {
    // Hər tələbə fərqli variant seçir: bəziləri düz, bəziləri səhv.
    const choice = (i % 2 === 0) ? 2 : 1;   // B düzgündür (index 1)
    const btn = await p.$(`#options button:nth-child(${choice})`);
    if (btn) await btn.click().catch(() => {});
  }));
  await host.waitForTimeout(900);
  // Növbəti suala keç
  await Promise.all(students.map(async (p) => {
    const next = await p.$('#nextBtn');
    if (next && await next.isVisible().catch(() => false)) await next.click().catch(() => {});
  }));
  await host.waitForTimeout(700);
}

await host.waitForTimeout(2500);
console.log('gedişat    :', await host.$$eval('#participants .row span', els => els.map(e => e.textContent)));
console.log('bitdi kartı:', await host.$eval('#finishedCard', e => !e.hidden).catch(() => 'yoxdur'));
console.log('liderlik   :', await host.$$eval('#leaderboard .row', els => els.map(e => {
    const parts = [...e.querySelectorAll('span')].map(s => s.textContent.trim());
    return parts.join(' | ');
  })).catch(() => []));
await host.screenshot({ path: 'multi-host.png', fullPage: true });
if (students[0]) await students[0].screenshot({ path: 'multi-student.png', fullPage: true });
console.log('JS xətaları:', errs.length ? errs.slice(0, 5) : 'yoxdur');
await b.close();
