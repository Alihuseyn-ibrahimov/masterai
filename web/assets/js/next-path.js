/* Girişdən sonra qayıdış ünvanı (MasterAI Classroom, gün 6).
 *
 * Tələbə sinifdə QR kodu skan edir, amma telefonda daxil olmayıb: giriş
 * səhifəsindən sonra QR linkinə QAYITMALIDIR, yoxsa davamiyyət yazılmaz.
 * Yalnız saytın öz səhifəsinə (`ad.html?…`) qayıdılır: başqa domenə
 * yönləndirmə (açıq redirect) mümkün deyil. DOM tələb etmir.
 */

const KEY = 'masterai.next';
const SAFE = /^[a-z0-9-]+\.html(\?[^#\s]*)?$/;

/** Təhlükəsiz nisbi yol və ya `null`. */
export function safeNextPath(value) {
  if (typeof value !== 'string') return null;
  const path = value.replace(/^\/+/, '');
  return SAFE.test(path) ? path : null;
}

export function rememberNext(storage, path) {
  const safe = safeNextPath(path);
  if (!safe) return;
  try {
    storage.setItem(KEY, safe);
  } catch (e) { /* yaddaş bloklanıb - qayıdış olmayacaq */ }
}

/** Bir dəfəlikdir: oxunan kimi silinir. */
export function takeNext(storage) {
  try {
    const value = storage.getItem(KEY);
    storage.removeItem(KEY);
    return safeNextPath(value);
  } catch (e) {
    return null;
  }
}
