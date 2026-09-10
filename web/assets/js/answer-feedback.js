/* Cavabdan sonra göstərilən geri bildirim - ev tapşırığı və canlı
 * sessiya üçün EYNİ mətn.
 *
 * NİYƏ: hər iki ekran yalnız «Düzgün cavab: B» yazırdı. Geri bildirim
 * kartı açılanda variantlar artıq ekranda OLMUR, yəni tələbə B-nin nə
 * olduğunu xatırlamalıdır. Səhv cavabdan öyrənmək bu ekranın yeganə
 * məqsədidir - hərf onu vermir.
 */

const LETTERS = 'ABCDE';

function letter(index) {
  return LETTERS[index] ?? '-';
}

function optionLine(prefix, options, index) {
  const mark = letter(index);
  const text = Array.isArray(options) ? options[index] : null;
  return text ? `${prefix}: ${mark}. ${text}` : `${prefix}: ${mark}`;
}

/**
 * @param {{options: string[]|null, correctIndex: number,
 *          chosenIndex: number|null, isCorrect: boolean}} input
 * @returns {{badge: {className, label}, correctLine: string,
 *           chosenLine: string|null}}
 *   `chosenLine` düzgün cavabda `null` - eyni şeyi iki dəfə yazmaq
 *   ekranı doldurur, heç nə əlavə etmir.
 */
export function answerFeedback({ options, correctIndex, chosenIndex, isCorrect }) {
  const badge = isCorrect
    ? { className: 'badge badge--success', label: 'Düzgün' }
    : { className: 'badge badge--danger', label: 'Səhv' };
  const chosenLine = (!isCorrect && Number.isInteger(chosenIndex))
    ? optionLine('Sizin cavabınız', options, chosenIndex) : null;
  return { badge, correctLine: optionLine('Düzgün cavab', options, correctIndex), chosenLine };
}

/** Yekun nəticə. Məxrəcsiz xal mənasızdır; ümumi say bilinmirsə faiz
 *  UYDURULMUR. */
export function scoreLine(score, total) {
  if (!total) return `${score} düzgün cavab`;
  return `${score}/${total} düzgün cavab (${Math.round((score / total) * 100)}%)`;
}
