/* Görünüş seçimi (işıqlı / tünd / cihaza uyğun) - BÜTÜN səhifələr üçün.
 *
 * REAL BUG (2026-09-12): bu məntiq YALNIZ `profil.html`-in içində
 * yazılmışdı. Seçim `localStorage`-a düşürdü, amma başqa heç bir səhifə
 * onu OXUMURDU - istifadəçi tünd rejim seçir, çatlara keçən kimi ekran
 * yenidən işıqlı olurdu. Seçim itmirdi, sadəcə tətbiq olunmurdu.
 *
 * İKİ HİSSƏ VAR və bu ayrılıq QƏSDƏNDİR:
 *   1. Hər səhifənin `<head>`-ində KİÇİK inline skript - temanı ilk
 *      boyamadan ƏVVƏL tətbiq edir. Modul kimi yüklənsə, brauzer
 *      əvvəlcə işıqlı ekranı çəkər, sonra tündə keçər - hər keçiddə
 *      göz deşən ağ sıçrayış olar.
 *   2. Bu modul - seçimin oxunması/yazılması və profil ekranının
 *      məntiqi. Saf funksiyalar, testlə örtülüdür.
 *
 * `localStorage` Safari gizli rejimində ATIR - görünüş seçimi tətbiqi
 * sındırmamalıdır, ona görə hər əməliyyat `try/catch`-dədir.
 */

export const THEME_KEY = 'masterai-theme';
export const CHOICES = ['light', 'dark', 'system'];

/** Saxlanmış seçim. Yararsız dəyər `system` sayılır - bazaya kənardan
 *  düşmüş zibil ekranı sındırmamalıdır. */
export function readStoredTheme(storage = globalThis.localStorage) {
  try {
    const saved = storage.getItem(THEME_KEY);
    return (saved === 'light' || saved === 'dark') ? saved : 'system';
  } catch {
    return 'system';
  }
}

/** `system` seçimində atribut SİLİNİR - CSS-dəki
 *  `prefers-color-scheme` qaydası yalnız o zaman işə düşür. */
export function applyTheme(choice, root = document.documentElement) {
  if (choice === 'light' || choice === 'dark') root.setAttribute('data-theme', choice);
  else root.removeAttribute('data-theme');
  return choice;
}

/** Seçimi yazır və dərhal tətbiq edir. Yaddaş bloklanıbsa seçim yalnız
 *  bu səhifə üçün işləyir - istifadəçi heç olmasa nəticəni görür. */
export function setTheme(choice, { storage = globalThis.localStorage, root } = {}) {
  const value = CHOICES.includes(choice) ? choice : 'system';
  try {
    if (value === 'system') storage.removeItem(THEME_KEY);
    else storage.setItem(THEME_KEY, value);
  } catch { /* yaddaşsız davam edirik */ }
  return applyTheme(value, root);
}
