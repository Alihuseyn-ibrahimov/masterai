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


/* ---- Ev tapşırığı tərəqqisi ----
 * Tələbənin STATUS mətni backend-dən onsuz da Azərbaycanca gəlir
 * (`Literal["gözləyir", "davam edir", "tamamlanıb"]`), ona görə orada
 * tərcüməyə ehtiyac yoxdur.
 *
 * Burada həll olunan başqa problemdir: sinif üzrə tərəqqi nişanı hər
 * halda EYNİ mavi rəngdə idi, yəni 9/9 ilə 6/18 gözlə fərqlənmirdi, ona görə
 * müəllim geridə qalan sinfi tarayıb tapa bilmirdi.
 */

/**
 * Bütün sinif üzrə tərəqqi. Rəng vəziyyəti bildirir ki, müəllim
 * siyahını gözlə tarayıb geridə qalanı tapa bilsin; əvvəl hamısı eyni
 * mavi idi və 9/9 ilə 6/18 fərqlənmirdi.
 */
export function homeworkProgressBadge(completed, total) {
  const label = `${completed}/${total} tamamlayıb`;
  if (!total) return { className: 'badge badge--neutral', label: 'Üzv yoxdur' };
  if (completed >= total) return { className: 'badge badge--success', label };
  if (completed === 0) return { className: 'badge badge--neutral', label };
  return { className: 'badge badge--info', label };
}
