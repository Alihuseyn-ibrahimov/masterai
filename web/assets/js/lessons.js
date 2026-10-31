/* Dərs cədvəli - saf köməkçilər (MasterAI Classroom, gün 1).
 *
 * DOM tələb etmir, Node-da test olunur. Vaxt serverdə UTC saxlanır;
 * burada brauzerin YERLİ vaxtına çevrilir (tələbə Bakıdadırsa Bakı
 * vaxtı, xaricdədirsə öz vaxtı).
 */

const MONTHS = ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avq', 'sen', 'okt', 'noy', 'dek'];

export const MODE_LABELS = { online: 'Onlayn', offline: 'Sinifdə' };
export const STATUS_LABELS = { scheduled: 'Planlaşdırılıb', live: 'Canlı', ended: 'Bitib' };

function pad(n) {
  return String(n).padStart(2, '0');
}

/** «3 noy, 10:00» - yerli vaxtla. */
export function formatLessonTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** `<input type="datetime-local">` dəyəri (yerli vaxt, saniyəsiz) →
 *  saat qurşaqlı ISO. Boş və ya yararsız dəyər üçün `null`. */
export function localInputToIso(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/** Canlı dərslər əvvəldə, sonra gələcək (yaxın birinci), sonra
 *  keçmiş (ən yenisi birinci). `now` testlər üçün ötürülür. */
export function groupLessons(lessons, now = Date.now()) {
  const live = [];
  const upcoming = [];
  const past = [];
  for (const lesson of lessons || []) {
    if (lesson.status === 'live') live.push(lesson);
    else if (lesson.status === 'ended') past.push(lesson);
    else {
      const end = new Date(lesson.starts_at).getTime() + lesson.duration_min * 60000;
      (end < now ? past : upcoming).push(lesson);
    }
  }
  const at = (l) => new Date(l.starts_at).getTime();
  upcoming.sort((a, b) => at(a) - at(b));
  past.sort((a, b) => at(b) - at(a));
  return { live, upcoming, past };
}
