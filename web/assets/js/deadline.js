/* Son tarixin İNSAN dilində ifadəsi və təcililiyə görə sıralama.
 *
 * NİYƏ: ev tapşırığı kartı "son tarix: 2026-09-15" yazırdı. Tələbə bu
 * sətirdən "5 gün qalıb"ı özü hesablamır - baxıb keçir. Daha pisi:
 * gecikmiş tapşırıq da eyni sakit boz mətnlə görünürdü, yəni ekranda
 * TƏCİLİ olan heç nə yox idi.
 *
 * Tarixlər backend-dən `YYYY-MM-DD` kimi gəlir (`due_date`), saat
 * qurşağı daşımır - ona görə burada UTC gün nömrəsi ilə işləyirik.
 * `new Date('2026-09-15')` UTC gecəyarısı deməkdir; yerli vaxtla
 * müqayisə etsək qurşaqdan asılı olaraq bir gün sürüşərdi.
 */

const MS_PER_DAY = 86400000;
const _ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function utcDayNumber(isoDate) {
  if (typeof isoDate !== 'string' || !_ISO_DATE.test(isoDate)) return null;
  const value = Date.parse(`${isoDate}T00:00:00Z`);
  return Number.isNaN(value) ? null : Math.floor(value / MS_PER_DAY);
}

/** Bugünün ISO tarixi (yerli təqvimə görə - istifadəçi "bugün" deyəndə
 *  öz təqvimini nəzərdə tutur). */
export function todayIso(now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * Son tarixin nişanı. Yararsız/boş tarixdə `null` - kart tarix sətri
 * olmadan da göstərilməlidir.
 *
 * Rəng qəsdən pilləlidir: hər şeyi qırmızı etmək heç nəyi qırmızı
 * etməməklə eynidir.
 */
export function deadlineNote(dueDate, today = todayIso()) {
  const due = utcDayNumber(dueDate);
  const now = utcDayNumber(today);
  if (due === null || now === null) return null;

  const days = due - now;
  if (days < 0) {
    const late = -days;
    return { days, overdue: true, label: `${late} gün gecikib`, className: 'badge badge--danger' };
  }
  if (days === 0) {
    return { days, overdue: false, label: 'Bugün son gün', className: 'badge badge--danger' };
  }
  if (days === 1) {
    return { days, overdue: false, label: 'Sabah son gün', className: 'badge badge--warning' };
  }
  const className = days <= 3 ? 'badge badge--warning' : 'badge badge--neutral';
  return { days, overdue: false, label: `${days} gün qalıb`, className };
}

/**
 * Təcililiyə görə sıralama: gecikmiş və yaxın olanlar əvvəldə,
 * tamamlanmışlar sonda (onlar artıq iş deyil, arxivdir).
 *
 * Mənbə massivi DƏYİŞDİRİLMİR - çağıran eyni siyahını başqa yerdə də
 * işlədə bilər.
 */
export function sortByUrgency(assignments, today = todayIso()) {
  const done = (row) => (row.status === 'tamamlanıb' ? 1 : 0);
  // Tarixsiz sətir sona düşür, amma İTMİR.
  const key = (row) => {
    const day = utcDayNumber(row.due_date);
    return day === null ? Number.POSITIVE_INFINITY : day;
  };
  return [...(assignments || [])].sort((a, b) => {
    if (done(a) !== done(b)) return done(a) - done(b);
    // Tamamlanmışlarda ən yenisi əvvəldə: köhnə arxiv aşağı getsin.
    if (done(a) === 1) return key(b) - key(a);
    return key(a) - key(b);
  });
}
