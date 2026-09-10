/* Sual bankı kartı: YEGANƏ vizual tərif.
 *
 * NİYƏ AYRICA MODUL: eyni obyekt (sual bankı) iki səhifədə İKİ FƏRQLİ
 * şəkildə çızılırdı. Müəllim konsolunda statuslu, iki hərəkətli və
 * bərabər hündürlüklü kart; canlı sessiya səhifəsində isə statussuz,
 * tam enli düymə ilə başqa kart. Eyni şeyin iki görünüşü olması
 * tətbiqi «bir məhsul» kimi göstərmir.
 *
 * Hərəkətlər çağırandan gəlir, çünki səhifədən səhifəyə dəyişir;
 * dəyişməyən hissə (başlıq, status, fənn, sual sayı, düzülüş) isə burada
 * bir dəfə təyin olunur.
 */

import { statusBadge, subjectColorVar, subjectLabel } from './subjects.js';

/** Bir hərəkət: `{ label, href }` keçid, `{ label, onClick }` düymə.
 *  `primary: true` əsas hərəkəti bildirir (kartda ən çox biri olmalıdır). */
function createAction(action) {
  const variant = action.primary ? 'btn--primary' : 'btn--secondary';
  const node = document.createElement(action.href ? 'a' : 'button');
  node.className = `btn ${variant} btn--sm`;
  node.textContent = action.label;
  if (action.href) {
    node.href = action.href;
  } else {
    node.type = 'button';
    node.addEventListener('click', action.onClick);
  }
  return node;
}

/**
 * @param {object} set - `/live/question-sets` sətri
 * @param {object} [options]
 * @param {Array} [options.actions] - kartın altındakı hərəkətlər
 * @param {string} [options.note] - statusa aid izah (məs. gözlənti müddəti)
 * @returns {HTMLElement}
 */
export function createBankCard(set, options = {}) {
  const card = document.createElement('div');
  card.className = 'card card--subject bank';
  card.style.setProperty('--subject', subjectColorVar(set.subject));

  const head = document.createElement('div');
  head.className = 'bank__head';
  const title = document.createElement('h4');
  title.className = 'bank__title';
  title.textContent = set.title;
  head.append(title);

  if (options.showStatus !== false) {
    const badge = statusBadge(set.status);
    const status = document.createElement('span');
    status.className = badge.className;
    status.textContent = badge.label;
    head.append(status);
  }

  const meta = document.createElement('p');
  meta.className = 'bank__meta';
  meta.textContent = `${subjectLabel(set.subject)} · ${set.question_count} sual`;
  card.append(head, meta);

  if (options.note) {
    const note = document.createElement('p');
    note.className = 'bank__meta';
    note.textContent = options.note;
    card.append(note);
  }

  if (set.status === 'failed' && set.error) {
    const error = document.createElement('p');
    error.className = 'bank__error';
    error.textContent = set.error;
    card.append(error);
  }

  const actions = options.actions || [];
  if (actions.length) {
    const row = document.createElement('div');
    row.className = 'bank__actions';
    for (const action of actions) row.append(createAction(action));
    card.append(row);
  }
  return card;
}
