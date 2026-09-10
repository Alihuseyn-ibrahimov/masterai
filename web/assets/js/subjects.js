/* Fənn kataloqu - açar, etiket və rəng dəyişəni.
 *
 * Açarlar `server/question_set_store.py`-dəki `SUBJECTS` ilə EYNİ
 * olmalıdır; rəng dəyişənləri `tokens.css`-dəki `--subject-*` ilə.
 * Hər ikisi testlə yoxlanılır (`test_web_client_contract.py`). */

export const SUBJECTS = [
  { key: 'mentiq', label: 'Məntiq', cssVar: '--subject-mentiq' },
  { key: 'informatika', label: 'İnformatika', cssVar: '--subject-informatika' },
  { key: 'dunyagorusu', label: 'Dünyagörüşü', cssVar: '--subject-dunyagorusu' },
  { key: 'azerbaycan_dili', label: 'Azərbaycan dili', cssVar: '--subject-azerbaycan-dili' },
  { key: 'qanunvericilik', label: 'Qanunvericilik', cssVar: '--subject-qanunvericilik' },
  { key: 'xarici_dil', label: 'Xarici dil', cssVar: '--subject-xarici-dil' },
];

const BY_KEY = new Map(SUBJECTS.map((subject) => [subject.key, subject]));

export function subjectLabel(key) {
  const subject = BY_KEY.get(key);
  return subject ? subject.label : key || '-';
}

/** CSS-ə veriləcək dəyər: `var(--subject-mentiq)`. Naməlum fənndə
 *  əsas rəngə geri dönür ki, element rəngsiz qalmasın. */
export function subjectColorVar(key) {
  const subject = BY_KEY.get(key);
  return `var(${subject ? subject.cssVar : '--color-primary'})`;
}

/** Sual bankı statusunun nişan sinfi və etiketi. */
export function statusBadge(status) {
  if (status === 'ready') return { className: 'badge badge--success', label: 'Hazırdır' };
  if (status === 'failed') return { className: 'badge badge--danger', label: 'Uğursuz oldu' };
  return { className: 'badge badge--warning', label: 'Hazırlanır…' };
}
