/* Cavab variantlarının çəkilməsi - canlı sessiya VƏ ev tapşırığı üçün EYNİ.
 *
 * NİYƏ AYRICA MODUL: 2026-09-12-yə qədər hər iki ekran variantları
 * `btn btn--secondary btn--block` + sətiriçi `justify-content` hack-i
 * ilə çəkirdi, yəni:
 *   - ekranda beş bərabər boz düymə görünürdü (tədris tətbiqi hissi yox),
 *   - `components.css`-dəki `.option` anatomiyası HEÇ İŞLƏDİLMİRDİ,
 *   - eyni kod İKİ yerdə təkrarlanırdı.
 * Sonuncu bu layihədə artıq bir dəfə bahalı olub: geri bildirim mətni
 * iki ekranda ayrı yazılmışdı və düzəliş də iki yerdə edilməli oldu
 * (bax `answer-feedback.js` modul qeydi).
 *
 * Modul DOM yaradır, amma səhifəni ÖZÜ AXTARMIR - konteyner verilir.
 */

import { createIcon } from './icon.js';

const LETTERS = 'ABCDE';

/** A-E üçün beş ayrı rəng tokeni. Beşdən çox variant olsa rəng
 *  təkrarlanır - sual bankı 5 variantla işləyir, amma bu funksiya
 *  sayı sabit saymır. */
function optionColor(index) {
  return `var(--opt-${'abcde'[index % 5]})`;
}

export function optionLetter(index) {
  return LETTERS[index] ?? String(index + 1);
}

/**
 * Variant düymələrini çəkir.
 * @param {HTMLElement} container - `.option-list` sinfi tətbiq olunur
 * @param {string[]} options - variant mətnləri
 * @param {(index:number)=>void} onChoose
 * @returns {HTMLButtonElement[]}
 */
export function renderOptions(container, options, onChoose) {
  container.innerHTML = '';
  container.className = 'option-list';
  const buttons = [];

  (options || []).forEach((text, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'option';
    button.style.setProperty('--opt', optionColor(index));

    const letter = document.createElement('span');
    letter.className = 'option__letter';
    letter.setAttribute('aria-hidden', 'true');
    letter.textContent = optionLetter(index);

    const label = document.createElement('span');
    label.className = 'option__text';
    // QƏSDƏN textContent: variant mətni AI çıxışıdır, HTML kimi
    // şərh olunmamalıdır.
    label.textContent = text;

    const mark = document.createElement('span');
    mark.className = 'option__mark';
    mark.setAttribute('aria-hidden', 'true');

    button.append(letter, label, mark);
    // Ekran oxuyucu üçün hərf mətnin bir hissəsi olmalıdır, yoxsa
    // «Düzgün cavab: B» geri bildirimi ilə əlaqə qurula bilmir.
    button.setAttribute('aria-label', `${optionLetter(index)}. ${text}`);
    button.addEventListener('click', () => onChoose(index));
    container.append(button);
    buttons.push(button);
  });

  return buttons;
}

/** Toxunulan variantı işarələyir və hamısını bağlayır (ikiqat cavabın
 *  qarşısını alır - server ikincini xəta ilə rədd edir və istifadəçi
 *  səbəbini anlamır). */
export function markChosen(buttons, chosenIndex) {
  buttons.forEach((button, index) => {
    button.disabled = true;
    if (index === chosenIndex) button.classList.add('option--chosen');
  });
}

/** Cavab göndərilə bilmədi - vəziyyəti geri qaytarır. */
export function resetOptions(buttons) {
  buttons.forEach((button) => {
    button.disabled = false;
    button.classList.remove('option--chosen', 'option--correct', 'option--wrong');
    button.querySelector('.option__mark').replaceChildren();
  });
}

/**
 * Nəticəni variantların ÜSTÜNDƏ göstərir: düzgün olan yaşıl, seçilmiş
 * səhv olan qırmızı. Rəngdən ƏLAVƏ ikon (yoxlama/x) qoyulur - yalnız rəng
 * rəng korluğu olan istifadəçi üçün kifayət deyil.
 */
export function revealAnswer(buttons, { correctIndex, chosenIndex }) {
  buttons.forEach((button, index) => {
    button.classList.remove('option--chosen');
    const mark = button.querySelector('.option__mark');
    mark.replaceChildren();
    /* İkon sprite-dandır, EMOJİ DEYİL: emoji hər platformada fərqli
       görünür, `currentColor` ilə rənglənmir və ekran oxuyucusu onu
       mətn kimi oxuyur (bax `icon.js` modul qeydi). */
    if (index === correctIndex) {
      button.classList.add('option--correct');
      mark.append(createIcon('check'));
    } else if (index === chosenIndex) {
      button.classList.add('option--wrong');
      mark.append(createIcon('x'));
    }
  });
}

/** Sual-sual tərəqqi seqmentləri. `total` bilinmirsə heç nə çəkilmir -
 *  uydurma seqment sayı tələbəni çaşdırar. */
export function renderSteps(container, { total, currentIndex }) {
  container.innerHTML = '';
  if (!total || total < 1) return;
  container.className = 'quiz-steps';
  for (let i = 0; i < total; i += 1) {
    const item = document.createElement('span');
    item.className = 'quiz-steps__item';
    if (i < currentIndex) item.classList.add('quiz-steps__item--done');
    else if (i === currentIndex) item.classList.add('quiz-steps__item--current');
    container.append(item);
  }
}
