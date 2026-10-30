/* Dərs xülasəsi (Faza 3, 2026-10-30) - göstəriş və redaktə formatı.
 *
 * Redaktə QƏSDƏN sadə mətn sahələridir: hər sətir bir maddə, termin və
 * özünü-yoxla cütü isə «sol - sağ» sətri (ayırıcı boşluqlu defisdir,
 * «Qeyri-hökumət» kimi sözdaxili defis bölünmür). Hər maddə üçün ayrıca
 * input/sil düyməsi müəllimi yavaşladar; mətn sahəsində sətir silmək,
 * köçürmək və yapışdırmaq hamıya tanışdır.
 */

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

/* ---- DOM: oxu görünüşü (tələbə, müəllim önizləməsi, çap) ---- */

function section(title, node) {
  const wrap = document.createElement('section');
  wrap.className = 'stack stack--tight';
  const heading = document.createElement('h3');
  heading.textContent = title;
  wrap.append(heading, node);
  return wrap;
}

function bulletList(items) {
  const list = document.createElement('ul');
  list.className = 'stack stack--tight';
  for (const item of items) {
    const li = document.createElement('li');
    li.textContent = item;
    list.append(li);
  }
  return list;
}

/** Bütün mətn `textContent` ilə yazılır - AI çıxışı və müəllim redaktəsi
 *  HEÇ VAXT `innerHTML`-ə getmir. */
export function renderSummary(content) {
  const root = document.createElement('article');
  root.className = 'stack';

  const intro = document.createElement('p');
  intro.textContent = content.intro;
  root.append(intro);

  root.append(section('Əsas fikirlər', bulletList(content.key_points)));

  if (content.terms && content.terms.length) {
    const list = document.createElement('dl');
    list.className = 'stack stack--tight';
    for (const term of content.terms) {
      const dt = document.createElement('dt');
      const strong = document.createElement('strong');
      strong.textContent = term.term;
      dt.append(strong);
      const dd = document.createElement('dd');
      dd.className = 'text-muted';
      dd.textContent = term.definition;
      list.append(dt, dd);
    }
    root.append(section('Açar terminlər', list));
  }

  if (content.facts && content.facts.length) {
    root.append(section('Yadda saxla', bulletList(content.facts)));
  }

  if (content.self_check && content.self_check.length) {
    const list = document.createElement('ol');
    list.className = 'stack stack--tight';
    for (const item of content.self_check) {
      const li = document.createElement('li');
      const question = document.createElement('p');
      question.textContent = item.question;
      /* Cavab gizlidir: əvvəlcə özü düşünsün, sonra açsın. */
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.className = 'text-sm text-muted';
      summary.textContent = 'Cavabı göstər';
      const answer = document.createElement('p');
      answer.textContent = item.answer;
      details.append(summary, answer);
      li.append(question, details);
      list.append(li);
    }
    root.append(section('Özünü yoxla', list));
  }
  return root;
}
