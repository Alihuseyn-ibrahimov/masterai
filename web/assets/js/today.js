/* «Bu gün» ana ekranının hesablamaları - saf funksiyalar.
 *
 * NİYƏ: auditdə (2026-10-31) ana ekran YOX idi - tələbənin ilk bölməsi
 * «Çatlar», müəllimin ilk bölməsi «Quiz yarat» idi, canlı dərsə
 * qoşulmaq isə ekranın ən zəif hərəkəti idi. «Bu gün» bir baxışda
 * NÖVBƏTİ ADDIMI göstərir.
 *
 * Bütün rəqəmlər MÖVCUD datadandır, yeni backend sahəsi yoxdur:
 *   XP     = tarixçədəki düzgün cavab sayı x XP_PER_CORRECT
 *   seriya = tarixçədə fəallıq olan ardıcıl günlər (bu gün və ya dünən
 *            bitməlidir - dünən məşq edib bu gün hələ etməyən tələbənin
 *            seriyası səhər sıfırlanmamalıdır)
 * Uydurma rəqəm göstərilmir: data yoxdursa sıfırdır.
 */

export const XP_PER_CORRECT = 10;
/* Həftəlik hədəf: 30 düzgün cavab. 10 suallıq üç tapşırıq - kurs
 * ritminə (həftədə 2-3 dərs) uyğun, əlçatan hədəf. */
export const WEEKLY_GOAL_XP = 300;

const DAY_MS = 86400000;

function dayNumber(iso) {
  const text = String(iso || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
  const value = Date.UTC(Number(text.slice(0, 4)), Number(text.slice(5, 7)) - 1, Number(text.slice(8, 10)));
  return Number.isNaN(value) ? null : Math.round(value / DAY_MS);
}

/** Ardıcıl fəal günlər. `today` - `YYYY-MM-DD` (yerli gün). */
export function streakDays(entries, today) {
  const days = new Set();
  for (const entry of entries || []) {
    const day = dayNumber(entry && entry.date);
    if (day !== null) days.add(day);
  }
  const now = dayNumber(today);
  if (now === null || !days.size) return 0;
  let cursor = days.has(now) ? now : now - 1;
  let count = 0;
  while (days.has(cursor)) {
    count += 1;
    cursor -= 1;
  }
  return count;
}

/** Son `days` gündə (bu gün daxil) qazanılmış XP. */
export function xpSince(entries, today, days) {
  const now = dayNumber(today);
  if (now === null) return 0;
  let xp = 0;
  for (const entry of entries || []) {
    const day = dayNumber(entry && entry.date);
    if (day === null || day > now || day <= now - days) continue;
    xp += (Number(entry.score) || 0) * XP_PER_CORRECT;
  }
  return xp;
}

/** Həftəlik hədəfin faizi, 0-100 (hədəfi aşan 100-də dayanır). */
export function goalPercent(xp, goal = WEEKLY_GOAL_XP) {
  if (!(goal > 0)) return 0;
  return Math.max(0, Math.min(100, Math.round((Number(xp) || 0) / goal * 100)));
}

/**
 * Böyük kartda göstəriləcək dərs: canlı dərs varsa O, yoxdursa ən
 * yaxın gələcək dərs. Heç biri yoxdursa `null`.
 * `groupLessons`-un nəticəsini qəbul edir (lessons.js).
 */
export function heroLesson(groups) {
  if (groups && groups.live && groups.live.length) return { kind: 'live', lesson: groups.live[0] };
  if (groups && groups.upcoming && groups.upcoming.length) return { kind: 'next', lesson: groups.upcoming[0] };
  return null;
}

/**
 * Canlı/gələcək dərsin əsas düyməsi. Gələcək dərsə QOŞULMA düyməsi
 * VERİLMİR (auditdə tapılıb: planlaşdırılmış dərsdə «Dərs otağı»
 * görünürdü) - yalnız dərs səhifəsi.
 */
export function heroAction(hero) {
  if (!hero) return null;
  const id = encodeURIComponent(hero.lesson.id);
  if (hero.kind === 'live' && hero.lesson.mode === 'online') {
    return { label: 'Qoşul', href: `dars.html?id=${id}`, primary: true };
  }
  return { label: 'Dərs səhifəsi', href: `dersim.html?id=${id}`, primary: hero.kind === 'live' };
}

/** Hələ bitirilməmiş tapşırıqların ən təcilisi; yoxdursa `null`.
 *  `sorted` - `sortByUrgency`-dən keçmiş siyahı. */
export function nextHomework(sorted) {
  return (sorted || []).find((row) => row.status !== 'tamamlanıb') || null;
}

/** Kataloq sırası ilə ilk qazanılmamış nişan; hamısı qazanılıbsa `null`.
 *  `described` - `describeBadge`-dən keçmiş siyahı (kataloq sırasında). */
export function nextBadge(described) {
  return (described || []).find((badge) => !badge.earned) || null;
}

/** Qazanılmış nişan sayı. */
export function earnedCount(described) {
  return (described || []).filter((badge) => badge.earned).length;
}

/** Salamlama - adın yalnız birinci sözü. */
export function greeting(name) {
  const first = String(name || '').trim().split(/\s+/)[0];
  return first ? `Salam, ${first}` : 'Salam';
}
