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

/** Müəllimin «Başlat və gir» düyməsi bu qədər əvvəldən görünür: daha
 *  tez başlatmaq sinfə vaxtsız «Dərs başladı» mesajı göndərər. */
export const TEACHER_START_WINDOW_MIN = 60;

/**
 * Müəllimin böyük kartdakı düyməsi. Əvvəl həmişə «Dərslər»ə aparırdı:
 * onlayn dərsə girmək üçün başlat → səhifə yenilənir → «Dərs otağına gir»
 * → «Otağa gir», üç klik. İndi bir klik: `dars.html?start=1` başladır və
 * özü qoşulur. Sinif dərsinin idarəsi (QR) «Dərslər»dədir.
 */
export function teacherHeroAction(hero, now = new Date()) {
  if (!hero) return null;
  const { lesson } = hero;
  const id = encodeURIComponent(lesson.id);
  if (lesson.mode === 'online') {
    if (hero.kind === 'live') return { label: 'Dərs otağına gir', href: `dars.html?id=${id}`, primary: true };
    const minutes = (new Date(lesson.starts_at).getTime() - now.getTime()) / 60000;
    if (minutes <= TEACHER_START_WINDOW_MIN) {
      return { label: 'Başlat və gir', href: `dars.html?id=${id}&start=1`, primary: true };
    }
  }
  return { label: hero.kind === 'live' ? 'Dərsi idarə et' : 'Dərslərə bax', href: 'dersler.html', primary: true };
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

/* Son dərc olunmuş konspekt «Bu gün»də görünür. Səbəb: tələbə konspektdən
 * yalnız «Dərslər → Xülasələr»ə girəndə xəbər tuturdu. Oxundu/oxunmadı
 * izlənmir (backend sahəsi yoxdur), ona görə köhnə konspekt əbədi qalmasın
 * deyə yalnız son FRESH_SUMMARY_DAYS gün göstərilir. */
export const FRESH_SUMMARY_DAYS = 14;

/** Son `days` gündə dərc olunmuş ən yeni konspekt və neçə gün əvvəl. */
export function freshSummary(summaries, today, days = FRESH_SUMMARY_DAYS) {
  const now = dayNumber(today);
  if (now === null) return null;
  let best = null;
  for (const summary of summaries || []) {
    const day = dayNumber(summary && summary.published_at);
    if (day === null || day > now || day <= now - days) continue;
    if (!best || String(summary.published_at) > String(best.summary.published_at)) {
      best = { summary, ageDays: now - day };
    }
  }
  return best;
}

/** 0 → «Bu gün», 1 → «Dünən», N → «N gün əvvəl». */
export function ageText(ageDays) {
  if (ageDays <= 0) return 'Bu gün';
  if (ageDays === 1) return 'Dünən';
  return `${ageDays} gün əvvəl`;
}

/* Bayquşun «Bu gün»dəki cümləsi (Faza 4). Bir cümlə, ən faydalı xəbər:
 * bu günkü XP → gözləyən tapşırıq → seriya → ümumi salam. Tapşırıq adı
 * müəllimin mətnidir: ekrana textContent ilə yazılır, burada yalnız
 * uzunluğu kəsilir ki, nitq qutusu iki sətri aşmasın. */
const SAY_TITLE_MAX = 40;

export function mascotLine({ isTeacher = false, todayXp = 0, streak = 0, next = null } = {}) {
  if (isTeacher) return { state: 'idle', text: 'Dərsi siz keçin, konspekt və quizi mən hazırlayım.' };
  if (todayXp > 0) return { state: 'happy', text: `Bu gün +${todayXp} XP. Əla gedirsən!` };
  if (next && next.title) {
    const title = String(next.title);
    const short = title.length > SAY_TITLE_MAX ? `${title.slice(0, SAY_TITLE_MAX - 1).trimEnd()}…` : title;
    return { state: 'idle', text: `«${short}» səni gözləyir.` };
  }
  if (streak > 0) return { state: 'idle', text: `${streak} günlük seriyanı bu gün də davam etdir.` };
  return { state: 'idle', text: 'Bu gün nə öyrənirik?' };
}
