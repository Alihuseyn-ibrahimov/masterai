/* İnkişaf qrafikləri (Faza 3 PR 1, 2026-11-03) - DOM-suz məntiq.
 *
 * `GET /me/progress` / `GET /live/chats/{id}/progress` eyni formanı
 * ({weekly, by_subject, attendance}) qaytarır - render tələbə VƏ
 * müəllim ekranında eynidir. Qrafik üçün YENİ komponent yox - mövcud
 * `.progress`/`.progress__fill` zolağı (bax `components.css`) həftə/fənn
 * sətirləri üçün hazır idi.
 */

/** Göstəriləcək bir şey varmı? */
export function hasProgressData(data) {
  return Boolean(data && ((data.weekly && data.weekly.length) || (data.by_subject && data.by_subject.length)));
}

/** «02 Noy - 08 Noy» - `week_start` ISO tarixdir (bazar ertəsi). */
export function weekLabel(weekStart) {
  const start = new Date(`${weekStart}T00:00:00Z`);
  const end = new Date(start.getTime() + 6 * 24 * 60 * 60 * 1000);
  const fmt = (d) => d.toLocaleDateString('az-AZ', { day: '2-digit', month: 'short', timeZone: 'UTC' });
  return `${fmt(start)} - ${fmt(end)}`;
}

function barRow(label, percent, doc) {
  const row = doc.createElement('div');
  row.className = 'stack stack--tight';
  const head = doc.createElement('div');
  head.className = 'row row--between';
  const left = doc.createElement('span');
  left.className = 'text-sm';
  left.textContent = label;
  const right = doc.createElement('span');
  right.className = 'text-sm text-muted';
  right.textContent = `${percent}%`;
  head.append(left, right);
  const bar = doc.createElement('div');
  bar.className = 'progress';
  const fill = doc.createElement('div');
  fill.className = 'progress__fill';
  fill.style.setProperty('--progress', `${percent}%`);
  bar.append(fill);
  row.append(head, bar);
  return row;
}

export function renderWeekly(weekly, doc = document) {
  const wrap = doc.createElement('div');
  wrap.className = 'stack';
  for (const week of weekly) {
    wrap.append(barRow(weekLabel(week.week_start), week.percent, doc));
  }
  return wrap;
}

export function renderBySubject(bySubject, doc = document) {
  const wrap = doc.createElement('div');
  wrap.className = 'stack';
  for (const subject of bySubject) {
    wrap.append(barRow(subject.subject, subject.percent, doc));
  }
  return wrap;
}

/** Davamiyyət faizi mətni - dərs yoxdursa uydurma 0% yazılmır. */
export function attendanceLine(attendance) {
  if (!attendance || attendance.percent === null || attendance.percent === undefined) {
    return 'Hələ bitmiş dərs yoxdur.';
  }
  return `${attendance.attended}/${attendance.total} dərsdə iştirak (${attendance.percent}%)`;
}
