// Səhv Detektivi nəticəsinin mətnləri (`sehv.html`). DOM-suz: node testi ilə örtülüdür.
//
// Əsas qayda: «yoxlanmadı» heç vaxt «düzgündür» kimi göstərilmir, və YALNIZ modelin
// tapdığı səhv (sympy təsdiqləməyib) təklif kimi yazılır: v3 modeli düzgün həllərin
// ~41%-ini səhvli sayır, tələbə bunu qəti hökm kimi oxumamalıdır.

/** Domen kodu → ekranda ad. */
export const DOMAIN_LABELS = { riyaziyyat: 'Riyaziyyat', mentiq: 'Məntiq' };

const SUFFIX = ['cu', 'ci', 'ci', 'cü', 'cü', 'ci', 'cı', 'ci', 'ci', 'cu'];

/** 1 → «1-ci», 3 → «3-cü», 6 → «6-cı», 10 → «10-cu» (addım ≤ 15). */
export function ordinal(n) {
  return `${n}-${SUFFIX[n % 10]}`;
}

/** Nəticənin başlığı və vəziyyəti: { title, tone } (tone: correct | wrong | unknown). */
export function verdictOf(result) {
  if (result.status === 'error_found') {
    const name = result.error_name ? `: ${result.error_name}` : '';
    return { title: `${ordinal(result.wrong_step)} addımda səhv${name}`, tone: 'wrong' };
  }
  if (result.status === 'correct') return { title: 'Səhv tapılmadı', tone: 'correct' };
  return { title: 'Bu həlli yoxlaya bilmədik', tone: 'unknown' };
}

/** Qərarı kim verdi, nə qədər etibarlıdır - bir cümlə. */
export function sourceNote(result) {
  switch (result.source) {
    case 'sympy':
      return 'Addımlar hesabla (sympy) yoxlandı. Səhvin növünü yalnız AI model deyə bilər, o hazırda qoşulmayıb.';
    case 'model+sympy':
      return result.agreement === false
        ? 'AI model başqa nəticə verdi, amma hesab yoxlaması onu düzəltdi.'
        : 'AI modelin nəticəsini hesab yoxlaması da təsdiqlədi.';
    case 'model':
      return result.status === 'error_found'
        ? 'Bunu yalnız AI model deyir və model bəzən düzgün həlli də səhv sayır. Addımı özünüz yoxlayın.'
        : 'Bunu yalnız AI model deyir, hesabla yoxlanmayıb.';
    default:
      return result.model_error
        ? 'AI model cavab vermədi. Bir azdan yenidən yoxlayın.'
        : 'Hazırda yalnız hesab zəncirlərini (kəsr, ifadə, tənlik) yoxlaya bilirik. Məntiq və söz məsələləri üçün AI model qoşulmalıdır.';
  }
}

/** Addımın nişanı: { label, badge } və ya null (normal addım). */
export function stepMark(step) {
  if (step.status === 'wrong') return { label: 'İlk səhv', badge: 'badge--danger' };
  if (step.status === 'after_error') return { label: 'Səhvdən sonra', badge: 'badge--neutral' };
  return null;
}

/** Textarea mətni → addımlar (boş sətirlər atılır; «1)», «2.» nömrələrini server atır). */
export function splitSteps(text) {
  return String(text || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}
