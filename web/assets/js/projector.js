/* Proyektor rejimi (2026-10-31, «oyun enerjisi» PR 6).
 *
 * Müəllim canlı sessiya konsolunu lövhəyə/proyektora çıxarır. Ekran üç
 * mərhələdir: gözləmə (böyük PIN + QR + qoşulan adlar), gedişat (sayğac +
 * sinfin ümumi irəliləyişi) və nəticə (podium). Burada YALNIZ saf məntiq
 * var - DOM `sessiyalar.html`-dədir.
 *
 * Gedişatda fərdi xal GÖSTƏRİLMİR: ekranı bütün sinif görür, kimin geri
 * qaldığı lövhədə yazılmamalıdır. Yalnız «bitirdi» adları çıxır.
 */

/** «123456» → «123 456»: uzaqdan oxumaq və səslə demək asandır. */
export function formatPin(pin) {
  const digits = String(pin || '').replace(/\D/g, '');
  if (digits.length !== 6) return digits;
  return `${digits.slice(0, 3)} ${digits.slice(3)}`;
}

/** Linkdən sxemi atır: ekranda «masterai.prdostu.com/qosul.html» qalır. */
export function displayUrl(url) {
  return String(url || '').replace(/^https?:\/\//, '').replace(/\?.*$/, '');
}

/** Hansı mərhələ: `waiting` | `running` | `finished`. */
export function stagePhase({ started, finished }) {
  if (finished) return 'finished';
  if (started) return 'running';
  return 'waiting';
}

/** `participantRows` sətirlərindən sinfin ümumi gedişatı. */
export function classProgress(rows) {
  const list = rows || [];
  const answered = list.reduce((sum, row) => sum + Math.min(row.answered, row.total), 0);
  const total = list.reduce((sum, row) => sum + row.total, 0);
  const finishedNames = list.filter((row) => row.finished).map((row) => row.name);
  return {
    people: list.length,
    finished: finishedNames.length,
    finishedNames,
    percent: total > 0 ? Math.round((answered / total) * 100) : 0,
  };
}

/** Sərhədsiz uzun siyahı ekranı dolduracaq - qalanı «+N» kimi. */
export function visibleNames(names, limit) {
  const list = names || [];
  if (list.length <= limit) return { shown: list, more: 0 };
  return { shown: list.slice(0, limit), more: list.length - limit };
}

/** Yekun sıralamadan podium: ekranda 2-1-3 sırası ilə, qalanı siyahıda.
 *  Bərabər xallı tələbələr eyni yeri tutur (serverin sırası saxlanılır). */
export function podium(leaderboard) {
  const rows = (leaderboard || []).map((row) => ({
    name: row.display_name || `İştirakçı #${row.participant_id}`,
    score: row.correct_count ?? row.score ?? 0,
  }));
  let place = 0;
  rows.forEach((row, index) => {
    if (index === 0 || row.score !== rows[index - 1].score) place = index + 1;
    row.place = place;
  });
  const top = rows.slice(0, 3);
  const order = [top[1], top[0], top[2]].filter(Boolean);
  return { podium: order, rest: rows.slice(3) };
}
