/* Dərs xülasəsi (Faza 3, 2026-10-30) - göstəriş və redaktə formatı.
 *
 * Redaktə QƏSDƏN sadə mətn sahələridir: hər sətir bir maddə, termin və
 * özünü-yoxla cütü isə «sol - sağ» sətri (ayırıcı boşluqlu defisdir,
 * «Qeyri-hökumət» kimi sözdaxili defis bölünmür). Hər maddə üçün ayrıca
 * input/sil düyməsi müəllimi yavaşladar; mətn sahəsində sətir silmək,
 * köçürmək və yapışdırmaq hamıya tanışdır.
 */

import { createIcon } from './icon.js';

export const PAIR_SEPARATOR = ' - ';

/** Mətn sahəsi -> boş olmayan sətirlər. */
export function linesToList(text) {
  return String(text || '')
    .split('\n')
    .map((line) => line.replace(/^\s*[-•*]\s*/, '').trim())
    .filter(Boolean);
}

export function listToLines(items) {
  return (items || []).join('\n');
}

/** «sol - sağ» sətirləri -> [{[left]: .., [right]: ..}]. Yalnız İLK
 *  ayırıcıda bölünür - izahın içindəki « - » izahda qalır. Ayırıcısız
 *  sətir atılmır, sağ tərəf boş qalır. */
export function linesToPairs(text, left, right) {
  return linesToList(text).map((line) => {
    const at = line.indexOf(PAIR_SEPARATOR);
    if (at < 0) return { [left]: line, [right]: '' };
    return { [left]: line.slice(0, at).trim(), [right]: line.slice(at + PAIR_SEPARATOR.length).trim() };
  });
}

export function pairsToLines(pairs, left, right) {
  return (pairs || []).map((pair) => `${pair[left]}${PAIR_SEPARATOR}${pair[right]}`).join('\n');
}

/** Redaktə formasının dəyərləri -> `PUT /live/summaries/{id}` gövdəsi. */
export function contentFromForm(values) {
  return {
    title: String(values.title || '').trim(),
    intro: String(values.intro || '').trim(),
    key_points: linesToList(values.keyPoints),
    terms: linesToPairs(values.terms, 'term', 'definition'),
    facts: linesToList(values.facts),
    self_check: linesToPairs(values.selfCheck, 'question', 'answer'),
  };
}

/** Saxlamadan əvvəl yoxlama (server də 422 verir, bu - aydın mətn üçün). */
export function contentError(content) {
  if (!content.title) return 'Başlıq boş ola bilməz.';
  if (content.key_points.length < 2) return 'Ən azı 2 əsas fikir yazın.';
  return null;
}

/* ---- Kart üçün qısa göstəricilər (xulaseler.html) ---- */

/** «6 əsas fikir · 4 termin · 3 sual» - boş hissələr yazılmır. */
export function summaryStats(content) {
  if (!content) return '';
  return [
    [(content.key_points || []).length, 'əsas fikir'],
    [(content.terms || []).length, 'termin'],
    [(content.self_check || []).length, 'sual'],
  ].filter(([count]) => count > 0).map(([count, label]) => `${count} ${label}`).join(' · ');
}

/** Oxuma müddəti (dəqiqə, ən az 1) - dəqiqədə ~180 söz. */
export function readingMinutes(content) {
  if (!content) return 1;
  const parts = [content.title, content.intro, ...(content.key_points || []), ...(content.facts || []),
    ...(content.terms || []).flatMap((t) => [t.term, t.definition]),
    ...(content.self_check || []).flatMap((q) => [q.question, q.answer])];
  const words = parts.join(' ').split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 180));
}

/* ---- DOM: oxu görünüşü (tələbə, müəllim önizləməsi, çap) ----
 * 2026-10-31: düz siyahı idi (başlıq + nöqtəli sətirlər). İndi hər bölmə
 * ikonlu blokdur, əsas fikirlər nömrəli, «Yadda saxla» sarı vurğulu,
 * özünü yoxla sualları kartdır. Mətn yenə də YALNIZ textContent-dir. */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function section(title, icon, node, modifier) {
  const wrap = el('section', `summary-block${modifier ? ` summary-block--${modifier}` : ''}`);
  const head = el('div', 'summary-block__head');
  const tile = el('span', 'summary-block__icon');
  tile.append(createIcon(icon));
  head.append(tile, el('h3', '', title));
  wrap.append(head, node);
  return wrap;
}

function list(tag, className, items) {
  const node = el(tag, className);
  for (const item of items) node.append(el('li', '', item));
  return node;
}

/** Bütün mətn `textContent` ilə yazılır - AI çıxışı və müəllim redaktəsi
 *  HEÇ VAXT `innerHTML`-ə getmir. */
export function renderSummary(content) {
  const root = el('article', 'summary-doc');
  root.append(el('p', 'summary-doc__intro', content.intro));

  root.append(section('Əsas fikirlər', 'bolt', list('ol', 'summary-points', content.key_points)));

  if (content.terms && content.terms.length) {
    const terms = el('dl', 'summary-terms');
    for (const term of content.terms) {
      const row = el('div', 'summary-terms__row');
      row.append(el('dt', '', term.term), el('dd', '', term.definition));
      terms.append(row);
    }
    root.append(section('Açar terminlər', 'books', terms));
  }

  if (content.facts && content.facts.length) {
    root.append(section('Yadda saxla', 'star', list('ul', 'summary-facts', content.facts), 'facts'));
  }

  if (content.self_check && content.self_check.length) {
    const checks = el('ol', 'summary-checks');
    for (const item of content.self_check) {
      const li = el('li', 'summary-check');
      /* Cavab gizlidir: əvvəlcə özü düşünsün, sonra açsın. */
      const details = el('details');
      details.append(el('summary', 'summary-check__toggle', 'Cavabı göstər'), el('p', 'summary-check__answer', item.answer));
      li.append(el('p', 'summary-check__question', item.question), details);
      checks.append(li);
    }
    root.append(section('Özünü yoxla', 'target', checks));
  }
  return root;
}
