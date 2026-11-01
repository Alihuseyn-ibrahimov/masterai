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

/** «35 dəqiqə sonra», «2 saat 10 dəq sonra», «sabah, 10:00»,
 *  «3 gün sonra». Gələcək dərsə «Qoşul» verilmir - əvəzinə tələbə
 *  nə vaxt qayıtmalı olduğunu görür. Keçmiş vaxt üçün boş sətir:
 *  status hələ «scheduled»dırsa müəllim gecikir, bunu saymaq tələbəyə
 *  heç nə vermir. */
export function startsInText(iso, now = Date.now()) {
  const start = new Date(iso);
  const diff = start.getTime() - now;
  if (Number.isNaN(diff) || diff <= 0) return '';
  const minutes = Math.ceil(diff / 60000);
  if (minutes < 60) return `${minutes} dəqiqə sonra`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const today = new Date(now);
  const dayIndex = (d) => Math.floor(new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() / 86400000);
  const days = dayIndex(start) - dayIndex(today);
  if (days === 0) return rest ? `${hours} saat ${rest} dəq sonra` : `${hours} saat sonra`;
  if (days === 1) return `sabah, ${pad(start.getHours())}:${pad(start.getMinutes())}`;
  return `${days} gün sonra`;
}

function icsDate(ms) {
  return new Date(ms).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
}

function icsText(value) {
  return String(value ?? '').replace(/\\/g, '\\\\').replace(/;/g, '\\;')
    .replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');
}

/** Dərsi təqvimə əlavə etmək üçün .ics faylı (RFC 5545). Backend və
 *  bildiriş xidməti lazım deyil: telefonun öz təqvimi 15 dəqiqə əvvəl
 *  xatırladır. Sətirlər CRLF ilə bitir - Outlook LF-i qəbul etmir. */
export function lessonIcs(lesson, siteUrl, now = Date.now()) {
  const start = new Date(lesson.starts_at).getTime();
  if (Number.isNaN(start)) return '';
  const end = start + (Number(lesson.duration_min) || 60) * 60000;
  const url = `${siteUrl}/dersim.html?id=${encodeURIComponent(lesson.id)}`;
  const description = [lesson.chat_name, MODE_LABELS[lesson.mode], url].filter(Boolean).join('\n');
  return [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//MasterAI//Dərslər//AZ',
    'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT',
    `UID:lesson-${lesson.id}@masterai.prdostu.com`,
    `DTSTAMP:${icsDate(now)}`,
    `DTSTART:${icsDate(start)}`,
    `DTEND:${icsDate(end)}`,
    `SUMMARY:${icsText(lesson.title)}`,
    `DESCRIPTION:${icsText(description)}`,
    `URL:${url}`,
    'BEGIN:VALARM',
    'ACTION:DISPLAY',
    `DESCRIPTION:${icsText(lesson.title)}`,
    'TRIGGER:-PT15M',
    'END:VALARM',
    'END:VEVENT',
    'END:VCALENDAR',
    '',
  ].join('\r\n');
}

/** Brauzerdə .ics faylını endirir. DOM tələb edir, testdə çağırılmır. */
export function downloadLessonIcs(lesson, siteUrl) {
  const blob = new Blob([lessonIcs(lesson, siteUrl)], { type: 'text/calendar;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `ders-${lesson.id}.ics`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
