/* Dəvət kodunun brauzer tərəfi - `server/invite_code.py`-nin qarşılığı.
 *
 * NİYƏ HƏR İKİ TƏRƏFDƏ: server normallaşdırmanı onsuz da edir, amma
 * tələbə kodu YAZARKƏN görünüşün düzgün olması səhvi qabaqlayır -
 * ekranda `K7M-3QX` yazılıbsa, formada da elə görünməlidir.
 * Server yoxlaması bununla ƏVƏZLƏNMİR, sadəcə tamamlanır.
 *
 * Saf funksiyalardır - DOM yoxdur, ona görə `node --test` ilə birbaşa
 * yoxlanır.
 */

/** Əlifba `server/invite_code.py` ilə EYNİ olmalıdır. Oxşar simvollar
 *  (`0/O`, `1/I/L`) qəsdən yoxdur - kod sinifə səslə deyilir. */
export const CODE_ALPHABET = '23456789ABCDEFGHJKMNPQRSTUVWXYZ';
export const CODE_LENGTH = 6;

/** İstifadəçinin yazdığını saxlanan formata gətirir: böyük hərf,
 *  defissiz, boşluqsuz. Əlifbada olmayan simvollar ATILIR - tələbə
 *  `O` yazsa, onu sükutla `0`-a çevirmək daha pis olardı (səhv çat
 *  tapıla bilər), ona görə sadəcə düşür və kod natamam qalır. */
export function normalizeCode(raw) {
  if (typeof raw !== 'string') return '';
  const upper = raw.toUpperCase();
  let out = '';
  for (const char of upper) {
    if (CODE_ALPHABET.includes(char)) out += char;
  }
  return out.slice(0, CODE_LENGTH);
}

/** Göstəriş üçün: `K7M3QX` → `K7M-3QX`. Natamam kodda da işləyir,
 *  çünki istifadəçi yazarkən çağırılır. */
export function formatCode(code) {
  const normalized = normalizeCode(code);
  if (normalized.length <= 3) return normalized;
  return `${normalized.slice(0, 3)}-${normalized.slice(3)}`;
}

/** Serverə göndərməyə dəyərmi? Natamam kodla sorğu göndərmək yalnız
 *  sürət limitini yeyir - istifadəçi hələ yazmağı bitirməyib. */
export function isCompleteCode(raw) {
  return normalizeCode(raw).length === CODE_LENGTH;
}
