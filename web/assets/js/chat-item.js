/* Çat elementlərinin normallaşdırılması.
 *
 * Bu modul layihənin ən incə hissəsidir və səbəbi backend protokoludur:
 * EYNİ məntiqi element İKİ FƏRQLİ formada gəlir.
 *
 *   Tarixçə (`{type:"history", messages:[...]}`) - baza sətirləri:
 *     { id, chat_id, sender_id, kind, content, created_at }
 *     `content` mətn üçün sadə sətir, QALAN hər şey üçün JSON SƏTRİDİR.
 *
 *   Canlı hadisə - sahələr ƏN ÜST səviyyədədir, `message_id` ilə:
 *     { type:"quiz_question", question_id, question, options, message_id }
 *
 * Üstəlik `quiz_finished` tarixçədə `kind:"system"` kimi saxlanılır və
 * əsl növ JSON-un İÇİNDƏ (`{"kind":"quiz_finished",...}`) olur.
 *
 * Hər iki forma burada TƏK bir şəklə çevrilir ki, göstərmə kodu bu
 * fərqi ümumiyyətlə bilməsin.
 */

/** @typedef {'text'|'quiz_question'|'quiz_result'|'quiz_finished'|'system'} ChatItemKind */

function emptyItem(id, kind, senderId, createdAt) {
  return {
    id,
    kind,
    senderId: senderId ?? null,
    createdAt: createdAt ?? null,
    text: null,
    question: null,
    result: null,
    finished: null,
  };
}

function parseJsonContent(content) {
  if (typeof content !== 'string') return null;
  try {
    const parsed = JSON.parse(content);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    // Korlanmış qeyd bütün çatı sındırmamalıdır.
    return null;
  }
}

function fillQuestion(item, source) {
  item.question = {
    questionId: source.question_id ?? null,
    question: source.question ?? '',
    options: Array.isArray(source.options) ? source.options : [],
  };
  return item;
}

function fillResult(item, source) {
  item.result = {
    questionId: source.question_id ?? null,
    correctIndex: source.correct_index ?? null,
    explanation: source.explanation ?? '',
    answers: Array.isArray(source.answers) ? source.answers : [],
  };
  return item;
}

function fillFinished(item, source) {
  item.finished = {
    totalQuestions: source.total_questions ?? 0,
    // `scores` obyektdir: {"3": 5, "7": 4} - açarlar SƏTİRDİR (JSON).
    scores: source.scores && typeof source.scores === 'object' ? source.scores : {},
  };
  return item;
}

/** Tarixçə sətrini normal şəklə çevirir. Tanınmayan növ üçün `null`. */
export function normalizeHistoryRow(row) {
  if (!row || typeof row !== 'object') return null;
  const base = emptyItem(row.id, row.kind, row.sender_id, row.created_at);

  if (row.kind === 'text') {
    base.text = typeof row.content === 'string' ? row.content : '';
    return base;
  }

  const payload = parseJsonContent(row.content);
  if (!payload) {
    // JSON oxunmadısa element tamamilə atılmır - xam mətn kimi göstərilir
    // ki, çatda "boşluq" yaranmasın.
    base.kind = 'system';
    base.text = typeof row.content === 'string' ? row.content : '';
    return base;
  }

  if (row.kind === 'quiz_question') return fillQuestion(base, payload);
  if (row.kind === 'quiz_result') return fillResult(base, payload);

  if (row.kind === 'system') {
    // Yekun xülasə `system` kimi saxlanılır, əsl növ JSON-un içindədir.
    if (payload.kind === 'quiz_finished') {
      base.kind = 'quiz_finished';
      return fillFinished(base, payload);
    }
    base.text = typeof payload.kind === 'string' ? payload.kind : '';
    return base;
  }

  return base;
}

/** Canlı WS hadisəsini EYNİ normal şəklə çevirir. Element olmayan
 *  hadisələr (`history`, `error`) üçün `null`. */
export function normalizeLiveEvent(event) {
  if (!event || typeof event !== 'object') return null;

  if (event.type === 'message') {
    const item = emptyItem(event.id, 'text', event.sender_id, event.created_at);
    item.text = typeof event.content === 'string' ? event.content : '';
    return item;
  }

  // Canlı hadisələrdə element identifikatoru `message_id` adlanır.
  if (event.type === 'quiz_question') {
    return fillQuestion(emptyItem(event.message_id, 'quiz_question', null, null), event);
  }
  if (event.type === 'quiz_result') {
    return fillResult(emptyItem(event.message_id, 'quiz_result', null, null), event);
  }
  if (event.type === 'quiz_finished') {
    return fillFinished(emptyItem(event.message_id, 'quiz_finished', null, null), event);
  }

  return null;
}

/** Tarixçə siyahısını çevirir; oxunmayan sətirlər sükutla atılır. */
export function normalizeHistory(messages) {
  if (!Array.isArray(messages)) return [];
  return messages.map(normalizeHistoryRow).filter(Boolean);
}

/**
 * Elementi siyahıya əlavə edir; EYNİ `id` varsa əvəz edir.
 *
 * Bu, avtomatik yenidən qoşulma üçün ŞƏRTDİR: qoşulan kimi server
 * tarixçəni YENİDƏN göndərir, ondan sonra gələn canlı hadisələr
 * tarixçədəki elementlərlə üst-üstə düşə bilər. Dedupe olmasa çatda
 * təkrar mesajlar görünərdi.
 */
export function upsertItem(items, item) {
  if (!item) return items;
  const index = items.findIndex((existing) => existing.id != null && existing.id === item.id);
  if (index >= 0) {
    const copy = items.slice();
    copy[index] = item;
    return copy;
  }
  return items.concat([item]);
}
