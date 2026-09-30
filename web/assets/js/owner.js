/* Sahib paneli - saf göstəriş funksiyaları (spec 2026-09-29 §3).
 *
 * DOM-suz yazılıb ki, Node-da test edilsin. Səhifənin özü `sahib.html`-dədir.
 */

const DAY_MS = 24 * 60 * 60 * 1000;

/** Bazadakı `status` açıq/bağlı olmağı TƏK BAŞINA demir: `trial` və
 *  `active` tarix keçəndə bağlıdır (server `is_open` hesablayır). */
export function statusView(course) {
  if (course.status === 'owner') return { label: 'Müddətsiz', tone: 'neutral' };
  if (course.status === 'suspended') return { label: 'Dayandırılıb', tone: 'danger' };
  if (!course.is_open) return { label: 'Müddəti bitib', tone: 'warning' };
  if (course.status === 'active') return { label: 'Ödənilib', tone: 'success' };
  return { label: 'Sınaq', tone: 'info' };
}

export function daysLeftText(days) {
  if (days === null || days === undefined) return 'Müddətsiz';
  if (days <= 0) return 'Bitib';
  return `${days} gün qalıb`;
}

export function seatsText(students, limit) {
  return `${students} / ${limit === null || limit === undefined ? 'limitsiz' : limit}`;
}

export function activityText(activity) {
  return [
    `${activity.sessions} sessiya`,
    `${activity.question_sets} bank`,
    `${activity.answers} cavab`,
    `${activity.messages} mesaj`,
  ].join(' · ');
}

/** Təqvim günü ilə (saat fərqi yox): dünən axşam «Dünən»dir, «0 gün» yox. */
export function lastActivityText(iso, now = new Date()) {
  if (!iso) return 'Aktivlik yoxdur';
  const then = new Date(iso);
  const startOf = (d) => Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  const days = Math.round((startOf(now) - startOf(then)) / DAY_MS);
  if (days <= 0) return 'Bu gün';
  if (days === 1) return 'Dünən';
  return `${days} gün əvvəl`;
}

export function inviteUrl(origin, token) {
  return `${origin}/qeydiyyat.html?invite=${encodeURIComponent(token)}`;
}

const PROFILE_LABELS = { english: 'İngilis dili', exam_prep: 'İmtahana hazırlıq' };

export function profileLabel(profile) {
  return PROFILE_LABELS[profile] || profile;
}

const AUDIT_LABELS = {
  create: 'Kurs yaradıldı',
  payment: 'Ödəniş',
  suspend: 'Dayandırıldı',
  resume: 'Bərpa edildi',
  update: 'Parametrlər',
  join_code: 'Tələbə kodu',
  teacher_invite: 'Müəllim dəvəti',
};

export function auditActionLabel(action) {
  return AUDIT_LABELS[action] || action;
}
