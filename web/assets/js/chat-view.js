/* Çat elementlərinin göstərilməsi.
 *
 * Saf funksiyalar (ad axtarışı, vaxt formatı, xal cədvəli) ayrıca
 * saxlanılır ki, Node-da test edilə bilsinlər — DOM tələb etmirlər.
 *
 * TƏHLÜKƏSİZLİK: istifadəçi mətni HEÇ VAXT `innerHTML`-ə verilmir,
 * yalnız `textContent`. Çat məzmununu başqa istifadəçilər yazır.
 */

/** `GET /chats/{id}/members` cavabından id→ad xəritəsi. */
export function buildNameLookup(members) {
  const lookup = new Map();
  if (!Array.isArray(members)) return lookup;
  for (const member of members) {
    if (member && typeof member.user_id === 'number') {
      lookup.set(member.user_id, member.display_name || '');
    }
  }
  return lookup;
}

/** Göndərənin göstəriləcək adı.
 *
 *  Flutter tətbiqində ad kataloqu YOX idi və hər mesaj "İstifadəçi #3"
 *  kimi görünürdü (bax `app/README.md`). Burada `/chats/{id}/members`
 *  endpoint-i işlədilir; ad tapılmasa köhnə davranışa geri dönülür. */
export function displayNameFor(lookup, senderId, currentUserId) {
  if (senderId == null) return 'Sistem';
  if (senderId === currentUserId) return 'Siz';
  const name = lookup.get(senderId);
  return name || `İstifadəçi #${senderId}`;
}

/** ISO vaxtından yalnız saat:dəqiqə. Yararsız dəyərdə boş sətir —
 *  çatda "Invalid Date" görünməməlidir. */
export function formatTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${hours}:${minutes}`;
}

/** Yekun xal cədvəlini çoxdan aza sıralayır və adları qoşur.
 *  `scores` açarları JSON-dan gəldiyi üçün SƏTİRDİR. */
export function scoreboardRows(finished, lookup, currentUserId) {
  if (!finished || !finished.scores) return [];
  return Object.entries(finished.scores)
    .map(([userId, score]) => ({
      userId: Number(userId),
      score,
      name: displayNameFor(lookup, Number(userId), currentUserId),
    }))
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name, 'az'));
}

/** İstifadəçinin bu suala artıq cavab verib-vermədiyi — nəticə
 *  elementindən oxunur. Cavab verilmiş sual yenidən aktiv görünməməlidir
 *  (Flutter-də bu, real bug idi: çat yenidən açılanda cavablanmış kart
 *  aktiv qalırdı və toxunanda backend "artıq cavablanıb" xətası verirdi). */
export function answeredQuestionIds(items) {
  const answered = new Set();
  for (const item of items) {
    if (item.kind === 'quiz_result' && item.result && item.result.questionId != null) {
      answered.add(item.result.questionId);
    }
  }
  return answered;
}

/* ---- DOM ---- */

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text; // qəsdən textContent
  return node;
}

function renderTextItem(item, context) {
  const card = element('div', 'card stack stack--tight');
  const head = element('div', 'row row--between');
  head.append(
    element('span', 'text-sm', displayNameFor(context.lookup, item.senderId, context.userId)),
    element('span', 'text-xs text-faint', formatTime(item.createdAt)),
  );
  const body = element('p', null, item.text || '');
  card.append(head, body);
  return card;
}

function renderQuestionItem(item, context) {
  const card = element('div', 'card stack card--subject');
  card.style.setProperty('--subject', 'var(--color-primary)');
  card.append(element('span', 'badge badge--info', 'Sual'));
  card.append(element('h4', null, item.question.question));

  const alreadyAnswered = context.answered.has(item.question.questionId);
  const options = element('div', 'stack stack--tight');
  item.question.options.forEach((option, index) => {
    const button = element('button', 'btn btn--secondary', `${'ABCDE'[index] || index + 1}. ${option}`);
    button.type = 'button';
    button.style.justifyContent = 'flex-start';
    if (alreadyAnswered) {
      button.disabled = true;
    } else {
      button.addEventListener('click', () => context.onAnswer(item.question.questionId, index));
    }
    options.append(button);
  });
  card.append(options);
  if (alreadyAnswered) card.append(element('p', 'text-xs text-muted', 'Bu sual cavablanıb.'));
  return card;
}

function renderResultItem(item, context) {
  const card = element('div', 'card stack stack--tight');
  card.append(element('span', 'badge badge--success', 'Nəticə'));
  const letter = 'ABCDE'[item.result.correctIndex];
  card.append(element('p', null, `Düzgün cavab: ${letter != null ? letter : '—'}`));
  if (item.result.explanation) {
    card.append(element('p', 'text-sm text-muted', item.result.explanation));
  }
  const mine = item.result.answers.find((answer) => answer.user_id === context.userId);
  if (mine) {
    card.append(element(
      'span',
      mine.is_correct ? 'badge badge--success' : 'badge badge--danger',
      mine.is_correct ? 'Düzgün cavabladınız' : 'Səhv cavabladınız',
    ));
  }
  return card;
}

function renderFinishedItem(item, context) {
  const card = element('div', 'card stack stack--tight');
  card.append(element('span', 'badge badge--neutral', 'Quiz bitdi'));
  card.append(element('p', 'text-sm text-muted', `Ümumi sual: ${item.finished.totalQuestions}`));
  const rows = scoreboardRows(item.finished, context.lookup, context.userId);
  for (const row of rows) {
    const line = element('div', 'row row--between');
    line.append(
      element('span', 'text-sm', row.name),
      element('span', 'text-sm', `${row.score}/${item.finished.totalQuestions}`),
    );
    card.append(line);
  }
  return card;
}

export function renderItem(item, context) {
  if (item.kind === 'text') return renderTextItem(item, context);
  if (item.kind === 'quiz_question') return renderQuestionItem(item, context);
  if (item.kind === 'quiz_result') return renderResultItem(item, context);
  if (item.kind === 'quiz_finished') return renderFinishedItem(item, context);
  return element('p', 'text-xs text-faint', item.text || '');
}

export function renderItems(container, items, context) {
  container.innerHTML = '';
  if (!items.length) {
    const state = element('div', 'state');
    state.append(
      element('div', 'state__icon', '💬'),
      element('div', 'state__title', 'Hələ mesaj yoxdur'),
      element('div', 'state__text', 'İlk mesajı siz yazın və ya müəllimin quiz başlatmasını gözləyin.'),
    );
    container.append(state);
    return;
  }
  const enriched = { ...context, answered: answeredQuestionIds(items) };
  for (const item of items) container.append(renderItem(item, enriched));
}
