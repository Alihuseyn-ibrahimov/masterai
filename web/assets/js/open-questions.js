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
