/* Çətinlik bölgüsü (Faza 2, 2026-10-30) - DOM-suz məntiq.
 *
 * Müəllim yükləmədə asan/orta/çətin faizini yazır; backend eyni yoxlamanı
 * `pipeline/difficulty.py::validate_mix`-də edir. Burada yoxlama yalnız
 * müəllimə səhvi GÖNDƏRMƏDƏN göstərmək üçündür.
 */

export const LEVELS = ['asan', 'orta', 'çətin'];
export const DEFAULT_MIX = [30, 50, 20];

const LABELS = { asan: 'Asan', orta: 'Orta', 'çətin': 'Çətin' };
// Yaşıl («success») QƏSDƏN işlədilmir: sual kartında yaşıl «Düzgün»
// siqnalıdır, «Asan» onunla qarışardı.
const BADGES = { asan: 'badge--info', orta: 'badge--neutral', 'çətin': 'badge--warning' };

export function levelLabel(level) {
  return LABELS[level] || 'Səviyyəsiz';
}

export function levelBadgeClass(level) {
  // Səviyyəsiz (köhnə) sual nişan deyil, sönük mətndir - «orta» ilə qarışmasın.
  return BADGES[level] ? `badge ${BADGES[level]}` : 'text-xs text-faint';
}

/** Xəta mətni və ya `null` (bölgü düzgündürsə). */
export function mixError(values) {
  // Boş sahə `Number('')` ilə 0 olardı - səhvən «0%» kimi qəbul edilməsin.
  const numbers = values.map((value) => (String(value).trim() === '' ? NaN : Number(value)));
  if (numbers.some((n) => !Number.isInteger(n) || n < 0 || n > 100)) {
    return 'Hər faiz 0 ilə 100 arasında tam ədəd olmalıdır.';
  }
  const sum = numbers.reduce((a, b) => a + b, 0);
  if (sum !== 100) return `Faizlərin cəmi 100 olmalıdır (indi ${sum}).`;
  return null;
}

/** "30/50/20" -> [30, 50, 20]; köhnə bankda (null) və ya pozuq dəyərdə null. */
export function parseMix(text) {
  if (typeof text !== 'string') return null;
  const parts = text.split('/').map(Number);
  if (parts.length !== 3 || mixError(parts)) return null;
  return parts;
}

/** Sualların səviyyə sayı. Səviyyəsiz (köhnə) suallar ayrıca sayılır. */
export function countLevels(questions) {
  const counts = { asan: 0, orta: 0, 'çətin': 0, none: 0 };
  for (const question of questions || []) {
    const key = LEVELS.includes(question.difficulty) ? question.difficulty : 'none';
    counts[key] += 1;
  }
  return counts;
}

/** «3 asan · 5 orta · 2 çətin (istənilən 30/50/20)» */
export function summaryLine(questions, mixText) {
  const counts = countLevels(questions);
  let line = LEVELS.map((level) => `${counts[level]} ${level}`).join(' · ');
  if (counts.none) line += ` · ${counts.none} səviyyəsiz`;
  const mix = parseMix(mixText);
  if (mix) line += ` (istənilən ${mix.join('/')})`;
  return line;
}

/* ---- Hesabat: səviyyə üzrə nəticə (canlı sessiya + ev tapşırığı) ---- */

/** Düzgün cavab faizi; cavab yoxdursa `null` (0% ilə qarışmasın). */
export function statPercent(stat) {
  if (!stat || !stat.total_answers) return null;
  return Math.round((stat.correct_count / stat.total_answers) * 100);
}

/** Bir sətir mətni: [sol, sağ]. */
export function statLine(stat) {
  const left = `${levelLabel(stat.level)} · ${stat.question_count} sual`;
  const percent = statPercent(stat);
  return [left, percent === null ? 'cavab yoxdur' : `${percent}% düzgün`];
}

/** Göstəriləcək bir şey varmı? Yalnız səviyyəsiz suallar (köhnə bank)
 *  olanda blok mənasızdır - müqayisə ediləcək səviyyə yoxdur. */
export function hasLevelStats(stats) {
  return (stats || []).some((stat) => LEVELS.includes(stat.level));
}

export function renderDifficultyStats(stats) {
  const wrap = document.createElement('div');
  wrap.className = 'stack stack--tight';
  const title = document.createElement('p');
  title.className = 'text-sm text-muted';
  title.textContent = 'Çətinlik üzrə nəticə';
  wrap.append(title);
  for (const stat of stats) {
    const [leftText, rightText] = statLine(stat);
    const line = document.createElement('div');
    line.className = 'row row--between';
    const left = document.createElement('span');
    left.className = levelBadgeClass(stat.level);
    left.textContent = leftText;
    const right = document.createElement('span');
    right.className = 'text-sm';
    right.textContent = rightText;
    line.append(left, right);
    wrap.append(line);
  }
  return wrap;
}

/** Gün 15: PyTorch modelinin proqnozu. «Model: ~40% düzgün cavab gözlənilir → Çətin».
 *  Model AI-nın səviyyəsi ilə razılaşmırsa bunu da deyir; proqnoz yoxdursa null. */
export function predictionLine(question) {
  const p = question && question.predicted_correct;
  if (typeof p !== 'number' || !LEVELS.includes(question.predicted_difficulty)) return null;
  let line = `Model: ~${Math.round(p * 100)}% düzgün cavab gözlənilir → ${levelLabel(question.predicted_difficulty)}`;
  if (LEVELS.includes(question.difficulty) && question.difficulty !== question.predicted_difficulty) {
    line += ` (AI «${levelLabel(question.difficulty)}» demişdi)`;
  }
  return line;
}
