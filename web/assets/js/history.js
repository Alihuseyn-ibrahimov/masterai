/* Tələbə tarixçəsinin xülasəsi.
 *
 * NİYƏ: `tarixce.html` yalnız nəticələrin siyahısını verirdi. Siyahı
 * "nə oldu"nu deyir, "nə etməliyəm"i yox. Tələbəyə lazım olan bir
 * cümlədir: hansı fənndə geridəyəm?
 *
 * Ehtiyatlılıq QƏSDƏNDİR: az data üzərində "zəif fənn" elan etmək
 * tələbəni səhv yerə yönəldər, yəni faydadan pis olar. Ona görə
 * aşağıdakı üç şərt eyni anda ödənməlidir.
 */

// Fənn "zəif" adlandırılmazdan əvvəl ən azı bu qədər nəticə olmalıdır.
const MIN_ENTRIES = 2;
// ...və ən azı bu qədər sual (2 nəticə x 2 sual hələ də azdır).
const MIN_QUESTIONS = 8;
// ...və ümumi faizdən ən azı bu qədər aşağı olmalıdır (faiz bəndi).
const MIN_GAP = 10;

function percentOf(score, total) {
  return total > 0 ? Math.round((score / total) * 100) : null;
}

/**
 * @param {Array} entries `/history/me` cavabı
 * @returns {{count, score, total, percent, bySubject, weakest}}
 *   `percent` və `weakest` data yetərsizdirsə `null` olur.
 */
export function historySummary(entries) {
  const rows = entries || [];
  const totals = new Map();
  let score = 0;
  let total = 0;

  for (const entry of rows) {
    const questions = Number(entry.total_questions) || 0;
    const correct = Number(entry.score) || 0;
    score += correct;
    total += questions;
    const current = totals.get(entry.subject) || { subject: entry.subject, score: 0, total: 0, count: 0 };
    current.score += correct;
    current.total += questions;
    current.count += 1;
    totals.set(entry.subject, current);
  }

  const bySubject = [...totals.values()]
    .map((row) => ({ ...row, percent: percentOf(row.score, row.total) }))
    // Zəifdən başlayır: tələbənin baxmalı olduğu sətir birincidir.
    .sort((a, b) => (a.percent ?? 101) - (b.percent ?? 101));

  const overall = percentOf(score, total);
  let weakest = null;
  if (overall !== null && bySubject.length > 1) {
    const candidate = bySubject[0];
    const enough = candidate.count >= MIN_ENTRIES
      && candidate.total >= MIN_QUESTIONS
      && candidate.percent !== null;
    if (enough && overall - candidate.percent >= MIN_GAP) weakest = candidate;
  }

  return { count: rows.length, score, total, percent: overall, bySubject, weakest };
}
