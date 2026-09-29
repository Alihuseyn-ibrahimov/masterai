/* Kurs lisenziyası - client tərəfi (spec 2026-09-29 §2).
 *
 * Server bağlı kursa HTTP 402 və WebSocket 4402 qaytarır. Hər ikisi
 * EYNİ səhifəyə aparır. Modul Node-da da işləyir (`node --test`), ona
 * görə `location` parametr kimi verilir və yoxdursa heç nə etmir.
 */

export const CLOSED_PAGE = 'bagli.html';
export const LICENSE_CLOSED_STATUS = 402;
export const LICENSE_CLOSED_WS_CODE = 4402;

/** Xəbərdarlıq həddi (gün) - spec: bitməyə 5 gün qalmış. */
export const EXPIRY_WARNING_DAYS = 5;

export function goToClosedPage(loc = globalThis.location) {
  if (!loc || typeof loc.replace !== 'function') return;
  // Bağlı səhifənin özü heç bir qorunan sorğu göndərmir, amma yenə də
  // döngüyə qarşı qoruma ucuzdur.
  if (String(loc.pathname || '').endsWith(`/${CLOSED_PAGE}`)) return;
  loc.replace(CLOSED_PAGE);
}

/** Banner yalnız müəllimə və yalnız müddətli kursda göstərilir.
 *  Tələbəyə göstərmək mənasızdır - ödəniş onun qərarı deyil. */
export function shouldShowExpiryBanner(user, course) {
  if (!user || !user.is_teacher || !course) return false;
  const days = course.days_left;
  return typeof days === 'number' && days <= EXPIRY_WARNING_DAYS;
}

export function expiryBannerText(days) {
  if (days <= 1) {
    return 'Kursun abunəsi 1 gün ərzində bitir. Davam etmək üçün ödənişi yeniləyin.';
  }
  return `Kursun abunəsinin bitməsinə ${days} gün qalıb. Davam etmək üçün ödənişi yeniləyin.`;
}
