/* Canlı sessiyanın ÇOXİŞTİRAKÇILI yük yoxlaması - ÇAT axını ilə.
 *
 * NİYƏ: real sinifdə 20-30 tələbə eyni anda qoşulur və eyni anda
 * cavablayır. `server/user_store.py` modul qeydindəki sqlite kilid
 * dərsi məhz bu ssenaridən gəlir.
 *
 * 2026-09-11-də PIN axını silindi, skript də çat axınına keçirildi:
 * tələbə artıq PIN yazmır, hesabı ilə daxil olur, çata qoşulma istəyi
 * göndərir, müəllim təsdiqləyir, sonra çatdakı sessiyaya girir.
 *
 * NƏ EDİR:
 *   1. API ilə QURAŞDIRMA (brauzersiz - bu hissə yoxlanılan deyil):
 *      çat yaradılır, N tələbə qeydiyyatdan keçir, kod ilə istək
 *      göndərir, müəllim TOPLU təsdiqləyir.
 *   2. BRAUZERDƏ yoxlama: müəllim çatdan sessiya başladır, N ayrı
 *      brauzer konteksti (ayrı localStorage, ayrı WebSocket = ayrı
 *      "cihaz") eyni anda qoşulur və eyni anda cavablayır.
 *
 * NƏ İSBAT ETMİR: bu, bir maşındakı brauzer kontekstləridir - real
 * şəbəkə gecikməsi, mobil rabitə və ayrı-ayrı telefonlar yoxdur.
 * Server tərəfin eyni anda gələn N bağlantını və N cavabı düzgün
 * emal etdiyini göstərir, şəbəkə davranışını YOX.
 *
 * İŞLƏTMƏK:
 *   1. Backend işə sal - 8125
 *   2. Statik sayt: .venv/bin/python -m http.server 8123 --directory web
 *   3. npm i playwright-core   (bir dəfə)
 *   4. node deploy/diagnostics/live_session_load.mjs <MÜƏLLİM_TOKENİ> <N> <SUAL_BANKI_ID>
 *
 * NƏTİCƏNİ MƏTNDƏN YOX, API-DƏN YOXLA (ən vacib qayda) - skript bunu
 * özü edir: sessiya hesabatını çəkir və hər sualda `total_answers`
 * iştirakçı sayına bərabərdirmi, xal həddi aşırmı - yoxlayır.
 */

/* playwright-core İŞLƏDİYİN QOVLUQDAN yüklənir, bu faylın yerindən YOX.
 * Səbəb: ESM `import` modulu faylın qovluğundan yuxarı axtarır, yəni
 * `masterai/`-də `node_modules` olmasa sınır. */
import { createRequire } from 'node:module';
const require = createRequire(`${process.cwd()}/`);
const { chromium } = require('playwright-core');

const token = process.argv[2];
const N = Number(process.argv[3] || 4);
const questionSetId = Number(process.argv[4] || 1);
const API = process.env.MASTERAI_API || 'http://127.0.0.1:8125';
const SITE = process.env.MASTERAI_SITE || 'http://127.0.0.1:8123';

if (!token) {
  console.error('İstifadə: node live_session_load.mjs <müəllim tokeni> <N> <sual bankı id>');
  process.exit(1);
}

const ADLAR = Array.from({ length: 40 }, (u, i) =>
  ['Aysel', 'Elvin', 'Nigar', 'Rəşad', 'Leyla', 'Tural', 'Günel', 'Orxan',
   'Sevinc', 'Kamran', 'Lalə', 'Fərid'][i % 12] + ' ' + (Math.floor(i / 12) + 1));

const api = async (path, { method = 'GET', body, bearer = token } = {}) => {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}: ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : null;
};

/* ---- 1. Quraşdırma (API) -------------------------------------- */

const stamp = Date.now();
const chat = await api('/chats', { method: 'POST', body: { kind: 'group', name: `Yük ${stamp}` } });
console.log(`çat: ${chat.id} | dəvət kodu: ${chat.invite_code}`);

const students = await Promise.all(Array.from({ length: N }, async (u, i) => {
  const auth = await api('/auth/register', {
    method: 'POST', bearer: null,
    body: { email: `yuk${stamp}_${i}@e2e.az`, password: 'Parol1234', display_name: ADLAR[i] },
  });
  // Sürət limiti istifadəçi ÜZRƏDİR (dəqiqədə 5), ona görə hər tələbənin
  // bir cəhdi limitə dəymir.
  await api('/chats/join-requests', {
    method: 'POST', bearer: auth.token, body: { code: chat.invite_code },
  });
  return auth;
}));

const approved = await api(`/chats/${chat.id}/join-requests/approve`, {
  method: 'POST', body: { user_ids: students.map((s) => s.user.id) },
});
console.log(`təsdiqlənən: ${approved.approved_user_ids.length}/${N}`);
if (approved.approved_user_ids.length !== N) {
  console.error('XƏBƏRDARLIQ: hamısı təsdiqlənmədi - nəticələr etibarsızdır');
}

/* ---- 2. Brauzer ------------------------------------------------ */

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const errs = [];

const redirect = async (ctx) => {
  await ctx.route((url) => url.pathname.endsWith('/assets/js/config.js'), async (route) => {
    const res = await route.fetch();
    const body = (await res.text())
      .replace("'https://masterai.prdostu.com'", `'${API}'`)
      .replace("'wss://masterai.prdostu.com'", `'${API.replace('http', 'ws')}'`);
    await route.fulfill({ status: 200, contentType: 'application/javascript', body });
  });
};
const watch = (p, who) => {
  p.on('pageerror', e => errs.push(`${who}: ${e.message}`));
  p.on('console', m => { if (m.type() === 'error') errs.push(`${who} konsol: ${m.text().slice(0, 80)}`); });
};
const seed = (ctx, t, user) => ctx.addInitScript(([tok, u]) => {
  try {
    localStorage.setItem('masterai.token', tok);
    localStorage.setItem('masterai.user', JSON.stringify(u));
  } catch (e) {}
}, [t, user]);

// ---- Müəllim: çatdan sessiya başladır ----
const hostCtx = await b.newContext({ viewport: { width: 1280, height: 900 } });
await seed(hostCtx, token, { id: 1, email: 'm@n.az', display_name: 'Müəllim', is_teacher: true, is_admin: false });
await redirect(hostCtx);
const host = await hostCtx.newPage();
watch(host, 'host');
await host.goto(`${SITE}/sessiyalar.html?questionSetId=${questionSetId}&chatId=${chat.id}`,
                { waitUntil: 'networkidle' });
await host.waitForTimeout(2000);

// Sessiya ID-sini MƏTNDƏN yox, API-dən götürürük.
const card = await api(`/chats/${chat.id}/live-session`);
if (!card) { console.error('sessiya yaranmadı - host səhifəsinə bax'); await b.close(); process.exit(1); }
const sessionId = card.session_id;
console.log(`sessiya: ${sessionId} | host: ${await host.$eval('#connStatus', e => e.textContent)}`);

// ---- N tələbə, EYNİ ANDA qoşulur ----
const pages = [];
const joinStart = Date.now();
await Promise.all(students.map(async (auth, i) => {
  const ctx = await b.newContext({ viewport: { width: 400, height: 850 } });
  await seed(ctx, auth.token, auth.user);
  await redirect(ctx);
  const p = await ctx.newPage();
  watch(p, ADLAR[i]);
  await p.goto(`${SITE}/sessiya.html?id=${sessionId}`, { waitUntil: 'networkidle' });
  pages[i] = p;
}));
await host.waitForTimeout(3500);
console.log('qoşulma müddəti:', Date.now() - joinStart, 'ms');
console.log('host ipucu :', await host.$eval('#startHint', e => e.textContent));

// ---- Başlat ----
await host.click('#startBtn');
await host.waitForTimeout(2000);

// ---- Hamısı EYNİ ANDA cavablayır ----
const questions = await api(`/live/question-sets/${questionSetId}/questions`);
const TOTAL = questions.length;
for (let q = 0; q < TOTAL; q += 1) {
  await Promise.all(pages.map(async (p, i) => {
    // Hər tələbə fərqli variant seçir: bəziləri düz, bəziləri səhv.
    const choice = (i % 2 === 0) ? 1 : 2;
    const btn = await p.$(`#options button:nth-child(${choice})`);
    if (btn) await btn.click().catch(() => {});
  }));
  await host.waitForTimeout(900);
  await Promise.all(pages.map(async (p) => {
    const next = await p.$('#nextBtn');
    if (next && await next.isVisible().catch(() => false)) await next.click().catch(() => {});
  }));
  await host.waitForTimeout(700);
}
await host.waitForTimeout(2500);

/* ---- 3. MƏNBƏDƏN yoxlama (mətnə görə yox) --------------------- */

const report = await api(`/live/sessions/${sessionId}/report`);
const problems = [];
for (const row of report.per_question) {
  if (row.total_answers !== N) {
    problems.push(`sual ${row.index}: ${row.total_answers}/${N} cavab - İTİB`);
  }
}
for (const row of report.rankings) {
  if (row.score > TOTAL) problems.push(`${row.display_name}: xal ${row.score} > ${TOTAL}`);
}
const names = report.rankings.map((r) => r.display_name);
if (new Set(names).size !== names.length) problems.push('təkrar iştirakçı adı var');
if (report.rankings.length !== N) {
  problems.push(`iştirakçı sayı ${report.rankings.length}, gözlənilən ${N}`);
}

console.log(`\nHESABAT (API-dən): ${TOTAL} sual, ${report.rankings.length} iştirakçı`);
for (const row of report.per_question) {
  console.log(`  sual ${row.index}: ${row.correct_count} düzgün / ${row.total_answers} cavab`);
}
const scores = report.rankings.map((r) => r.score);
console.log(`  xal aralığı: ${Math.min(...scores)}-${Math.max(...scores)}`);
console.log('JS xətaları:', errs.length ? errs.slice(0, 5) : 'yoxdur');
console.log(problems.length ? `\nPROBLEMLƏR:\n  ${problems.join('\n  ')}` : '\nPROBLEM YOXDUR ✓');

await host.screenshot({ path: 'multi-host.png', fullPage: true });
if (pages[0]) await pages[0].screenshot({ path: 'multi-student.png', fullPage: true });
await b.close();
process.exit(problems.length ? 1 : 0);
