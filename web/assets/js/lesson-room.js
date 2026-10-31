/* Canlı video dərsin saf köməkçiləri (Classroom, gün 2).
 *
 * LiveKit obyektlərindən asılı deyil - yalnız sadə dəyərlər alır ki,
 * Node-da test olunsun. Otaq məntiqinin özü `dars.html`-dədir.
 */

/** Kamerası sönük iştirakçının plitəsindəki hərf(lər): «Əli Həsənov» → «ƏH». */
export function initials(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  const letters = parts.length === 1 ? [parts[0]] : [parts[0], parts[parts.length - 1]];
  return letters.map((p) => p.charAt(0).toLocaleUpperCase('az')).join('');
}

/** Token-dəki `metadata` (`{"role": "teacher"}`) → rol. Yararsız və ya
 *  boş metadata tələbə sayılır: müəllim vurğusu yalnız serverin
 *  imzaladığı rolla verilir. */
export function roleOf(metadata) {
  try {
    return JSON.parse(metadata || '{}').role === 'teacher' ? 'teacher' : 'student';
  } catch {
    return 'student';
  }
}

/** Plitələrin sırası: ekran paylaşımı → müəllim → özüm → qalanlar ad üzrə. */
export function orderTiles(tiles) {
  const rank = (t) => (t.screen ? 0 : t.role === 'teacher' ? 1 : t.local ? 2 : 3);
  return [...tiles].sort((a, b) => rank(a) - rank(b) || String(a.name).localeCompare(String(b.name), 'az'));
}

/** Otaq bağlantısının vəziyyəti üçün mətn. */
export function connectionLabel(state) {
  return {
    connecting: 'Qoşulur…',
    connected: 'Canlı',
    reconnecting: 'Bağlantı bərpa olunur…',
    disconnected: 'Bağlantı kəsildi',
  }[state] || state;
}
