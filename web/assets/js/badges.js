/* Nişan kataloqu - açar, ad, ikon, meyar.
 *
 * Açarlar `server/app.py`-dəki `_BADGE_TYPES` ilə EYNİ olmalıdır
 * (testlə yoxlanılır). Meyar mətnləri `_evaluate_badges`-dəki real
 * şərtlərdən yazılıb - uydurma deyil:
 *   ilk_addim - ən azı bir nəticə
 *   yuz_faiz - bir nəticədə bütün suallar düzgün
 *   fenn_ustasi - bir fənndən 5 ev tapşırığı (_FENN_USTASI_MIN_COUNT)
 *   suretli_eqli - bir tapşırıq 3 dəqiqədən tez (_SURETLI_EQLI_MAX_MINUTES)
 *   silsile_5 - 5 fərqli gündə fəallıq (_SILSILE_MIN_DAYS)
 */

export const BADGES = [
  { key: 'ilk_addim', label: 'İlk addım', icon: 'seedling',
    criteria: 'İlk nəticənizi əldə edin' },
  { key: 'yuz_faiz', label: 'Yüz faiz', icon: 'percentage',
    criteria: 'Bir testin bütün suallarını düzgün cavablayın' },
  { key: 'fenn_ustasi', label: 'Fənn ustası', icon: 'school',
    criteria: 'Bir fənndən 5 ev tapşırığı tamamlayın' },
  { key: 'suretli_eqli', label: 'Sürətli əqli', icon: 'bolt',
    criteria: 'Bir tapşırığı 3 dəqiqədən tez bitirin' },
  { key: 'silsile_5', label: 'Silsilə', icon: 'flame',
    criteria: '5 fərqli gündə məşq edin' },
];

const BY_KEY = new Map(BADGES.map((badge) => [badge.key, badge]));

/** Serverdən gələn sətri kataloqla birləşdirir. Naməlum açar üçün də
 *  göstəriləcək bir şey qaytarır - backend yeni nişan əlavə edərsə
 *  ekran boş qalmasın. */
export function describeBadge(row) {
  const known = BY_KEY.get(row && row.badge_type);
  return {
    key: (row && row.badge_type) || '',
    label: known ? known.label : (row && row.badge_type) || 'Nişan',
    icon: known ? known.icon : 'award',
    criteria: known ? known.criteria : '',
    earned: Boolean(row && row.earned),
    earnedAt: (row && row.earned_at) || null,
  };
}

/** Qazanılanlar əvvəldə - istifadəçi öz nailiyyətini dərhal görsün. */
export function sortBadges(rows) {
  return (rows || [])
    .map(describeBadge)
    .sort((a, b) => Number(b.earned) - Number(a.earned));
}
