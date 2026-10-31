/* AI tutor cavabının göstərilməsi (gün 8). DOM tələb etmir, Node-da test olunur. */

const CITE = /\[(\d{1,2})\]/g;

/** «Mətn [1] davamı [2].» → [{text}, {cite: 1}, {text}, {cite: 2}, {text}] */
export function splitCitations(answer) {
  const parts = [];
  let last = 0;
  for (const match of String(answer || '').matchAll(CITE)) {
    if (match.index > last) parts.push({ text: answer.slice(last, match.index) });
    parts.push({ cite: Number(match[1]) });
    last = match.index + match[0].length;
  }
  if (last < String(answer || '').length) parts.push({ text: answer.slice(last) });
  return parts;
}

/** Mənbənin səhifəsi: dərs → dərs səhifəsi, konspekt → oxu səhifəsi. */
export function sourceHref(source) {
  if (source && source.lesson_id) return `dersim.html?id=${encodeURIComponent(source.lesson_id)}`;
  if (source && source.summary_id) return `xulase.html?id=${encodeURIComponent(source.summary_id)}`;
  return null;
}

export const HISTORY_LIMIT = 6;

/** Söhbətə yeni addım əlavə edir, yalnız son `HISTORY_LIMIT`-i saxlayır
 *  (gün 9: davam sualı üçün serverə göndərilir, server özü yadda saxlamır). */
export function pushTurn(history, role, text) {
  const value = String(text || '').trim();
  if (!value) return history.slice(-HISTORY_LIMIT);
  return [...history, { role, text: value.slice(0, 4000) }].slice(-HISTORY_LIMIT);
}

/** Tutorun cavabı tarixçədə necə görünür: quizdə sualın özü, «tapmadım»da heç nə. */
export function tutorTurnText(reply) {
  if (!reply) return '';
  if (reply.kind === 'quiz' && reply.quiz) return `Test sualı: ${reply.quiz.question}`;
  if (reply.kind === 'answer' || reply.kind === 'offtopic') return reply.answer || '';
  return '';
}
