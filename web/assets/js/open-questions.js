/* Açıq suallar (Faza 1 «Müəllim AI asistenti», 2026-11-03) - DOM-suz məntiq.
 *
 * Meyarlar (rubrika) redaktədə mətn kimi yazılır: hər sətir «bal | meyar».
 * Backend eyni həddləri yoxlayır (`UpdateOpenQuestionRequest`: 1-6 meyar,
 * hər biri 1-5 bal); burada yoxlama müəllimə səhvi göndərmədən göstərmək üçündür.
 */

export const MAX_RUBRIC_ITEMS = 6;
export const MAX_POINTS = 5;
export const MAX_COUNT = 15;

const KIND_LABELS = { qisa: 'Qısa cavab', esse: 'Esse' };

export function kindLabel(kind) {
  return KIND_LABELS[kind] || kind;
}

export function maxPoints(rubric) {
  return (rubric || []).reduce((sum, item) => sum + (Number(item.points) || 0), 0);
}

/** «2 bal» / «1 bal» - Azərbaycan dilində sayla isim tək qalır. */
export function pointsText(points) {
  return `${points} bal`;
}

export function rubricToLines(rubric) {
  return (rubric || []).map((item) => `${item.points} | ${item.criterion}`).join('\n');
}

/** Mətn → { rubric } və ya { error }. Boş sətirlər atılır. */
export function linesToRubric(text) {
  const lines = String(text || '').split('\n').map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return { error: 'Ən azı bir meyar yazın.' };
  if (lines.length > MAX_RUBRIC_ITEMS) return { error: `Ən çox ${MAX_RUBRIC_ITEMS} meyar ola bilər.` };
  const rubric = [];
  for (const [index, line] of lines.entries()) {
    const match = line.match(/^(\d+)\s*\|\s*(.+)$/);
    if (!match) return { error: `${index + 1}-ci sətir «bal | meyar» formatında deyil.` };
    const points = Number(match[1]);
    if (points < 1 || points > MAX_POINTS) {
      return { error: `${index + 1}-ci sətir: bal 1 ilə ${MAX_POINTS} arasında olmalıdır.` };
    }
    rubric.push({ points, criterion: match[2].trim() });
  }
  return { rubric };
}

/** «3 sual · 2 qısa cavab, 1 esse · cəmi 11 bal» */
export function setSummaryLine(items) {
  if (!items || !items.length) return '';
  const short = items.filter((item) => item.kind === 'qisa').length;
  const essay = items.length - short;
  const total = items.reduce((sum, item) => sum + (item.max_points || maxPoints(item.rubric)), 0);
  const kinds = [short && `${short} qısa cavab`, essay && `${essay} esse`].filter(Boolean).join(', ');
  return `${items.length} sual · ${kinds} · cəmi ${pointsText(total)}`;
}

/** Saya görə yoxlama: 1-15 tam ədəd. Xəta mətni və ya null. */
export function countError(value) {
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1 || n > MAX_COUNT) return `Sual sayı 1 ilə ${MAX_COUNT} arasında olmalıdır.`;
  return null;
}

/* ---- Açıq cavab (Faza 1, PR 2): tələbə və müəllim üçün vəziyyət mətni ---- */

/** Cavabın vəziyyətini bir cümlədə deyir. `audience`: 'student' | 'teacher'. */
export function answerStatusLine(answer, audience = 'student') {
  if (!answer) return '';
  const max = answer.max_points;
  switch (answer.status) {
    case 'grading':
      return 'AI cavabı yoxlayır…';
    case 'graded':
      return audience === 'teacher'
        ? `AI təklifi: ${answer.ai_points}/${max} bal · təsdiq gözləyir`
        : `AI təklifi: ${answer.ai_points}/${max} bal. Yekun balı müəllim təsdiqləyəcək.`;
    case 'failed':
      return audience === 'teacher'
        ? 'AI yoxlaya bilmədi · balı özünüz verin'
        : 'AI bu cavabı yoxlaya bilmədi, müəllim özü yoxlayacaq.';
    case 'confirmed':
      return `Yekun bal: ${answer.final_points}/${max}`;
    default:
      return '';
  }
}

/** «Müsabiqəni deyir: 1/2 bal - qismən» */
export function criterionLine(grade) {
  const head = `${grade.criterion}: ${grade.awarded}/${grade.points} bal`;
  return grade.comment ? `${head} - ${grade.comment}` : head;
}

/** Müəllim təsdiq formasının ilkin balı: AI təklifi, yoxdursa boş. */
export function suggestedPoints(answer) {
  if (!answer) return '';
  if (answer.final_points !== null && answer.final_points !== undefined) return String(answer.final_points);
  if (answer.ai_points !== null && answer.ai_points !== undefined) return String(answer.ai_points);
  return '';
}

/** Bal yoxlaması: 0..max tam ədəd. Xəta mətni və ya null. */
export function pointsError(value, max) {
  const n = Number(value);
  if (String(value).trim() === '' || !Number.isInteger(n) || n < 0 || n > max) {
    return `Bal 0 ilə ${max} arasında tam ədəd olmalıdır.`;
  }
  return null;
}
