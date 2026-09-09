/* Normallaşdırma testləri — real backend formaları ilə.
 *
 * Nümunələr uydurma DEYİL: `server/quiz_runner.py` və
 * `server/message_store.py`-dən oxunub. Backend protokolu dəyişsə bu
 * testlər sınmalıdır. */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  normalizeHistory,
  normalizeHistoryRow,
  normalizeLiveEvent,
  upsertItem,
} from '../assets/js/chat-item.js';

describe('tarixçə sətirləri', () => {
  test('mətn mesajı', () => {
    const item = normalizeHistoryRow({
      id: 5, chat_id: 1, sender_id: 3, kind: 'text',
      content: 'Salam, hazırsınız?', created_at: '2026-09-09T10:00:00',
    });
    assert.equal(item.kind, 'text');
    assert.equal(item.text, 'Salam, hazırsınız?');
    assert.equal(item.senderId, 3);
  });

  test('quiz sualı — content JSON SƏTRİDİR', () => {
    const item = normalizeHistoryRow({
      id: 6, sender_id: null, kind: 'quiz_question',
      content: JSON.stringify({
        question_id: 12, question: 'Paytaxt hansıdır?', options: ['Bakı', 'Gəncə'],
      }),
      created_at: '2026-09-09T10:01:00',
    });
    assert.equal(item.kind, 'quiz_question');
    assert.equal(item.question.questionId, 12);
    assert.equal(item.question.options.length, 2);
    assert.equal(item.senderId, null);
  });

  test('quiz nəticəsi', () => {
    const item = normalizeHistoryRow({
      id: 7, sender_id: null, kind: 'quiz_result',
      content: JSON.stringify({
        question_id: 12, correct_index: 0, explanation: 'Bakı paytaxtdır.',
        answers: [{ user_id: 3, chosen_index: 0, is_correct: true }],
      }),
    });
    assert.equal(item.result.correctIndex, 0);
    assert.equal(item.result.answers[0].is_correct, true);
  });

  test('quiz_finished tarixçədə `system` kimi saxlanılır, əsl növ JSON-un İÇİNDƏDİR', () => {
    // `_post_finish_summary` belə yazır — bu, asanlıqla gözdən qaçan yerdir.
    const item = normalizeHistoryRow({
      id: 8, sender_id: null, kind: 'system',
      content: JSON.stringify({ kind: 'quiz_finished', total_questions: 3, scores: { 3: 2 } }),
    });
    assert.equal(item.kind, 'quiz_finished');
    assert.equal(item.finished.totalQuestions, 3);
    assert.equal(item.finished.scores['3'], 2);
  });

  test('korlanmış JSON çatı sındırmır', () => {
    const item = normalizeHistoryRow({ id: 9, kind: 'quiz_question', content: '{yarımçıq' });
    assert.ok(item, 'element atılmamalıdır');
    assert.equal(item.kind, 'system');
  });

  test('etibarsız giriş üçün null', () => {
    assert.equal(normalizeHistoryRow(null), null);
    assert.equal(normalizeHistoryRow('mətn'), null);
  });

  test('siyahını çevirir, oxunmayanları atır', () => {
    const items = normalizeHistory([
      { id: 1, kind: 'text', content: 'a' },
      null,
      { id: 2, kind: 'text', content: 'b' },
    ]);
    assert.equal(items.length, 2);
  });

  test('massiv olmayan giriş boş siyahı verir', () => {
    assert.deepEqual(normalizeHistory(undefined), []);
  });
});

describe('canlı hadisələr', () => {
  test('mətn mesajı — `type:"message"` + sətir sahələri', () => {
    const item = normalizeLiveEvent({
      type: 'message', id: 10, chat_id: 1, sender_id: 4,
      kind: 'text', content: 'Salam', created_at: '2026-09-09T10:05:00',
    });
    assert.equal(item.kind, 'text');
    assert.equal(item.id, 10);
    assert.equal(item.senderId, 4);
  });

  test('quiz sualı — sahələr ƏN ÜST səviyyədə, id `message_id`-dir', () => {
    const item = normalizeLiveEvent({
      type: 'quiz_question', question_id: 12, question: 'Sual?',
      options: ['A', 'B'], message_id: 11,
    });
    assert.equal(item.id, 11, 'id `message_id`-dən gəlməlidir');
    assert.equal(item.question.question, 'Sual?');
  });

  test('quiz_finished canlıda ÖZ tipi ilə gəlir (tarixçədən fərqli)', () => {
    const item = normalizeLiveEvent({
      type: 'quiz_finished', total_questions: 5, scores: { 3: 4 }, message_id: 13,
    });
    assert.equal(item.kind, 'quiz_finished');
    assert.equal(item.finished.totalQuestions, 5);
  });

  test('element olmayan hadisələr üçün null', () => {
    assert.equal(normalizeLiveEvent({ type: 'history', messages: [] }), null);
    assert.equal(normalizeLiveEvent({ type: 'error', detail: 'səhv' }), null);
    assert.equal(normalizeLiveEvent(null), null);
  });

  test('EYNİ element tarixçədən və canlıdan eyni şəklə gəlir', () => {
    // Bu, bütün modulun mövcudluq səbəbidir.
    const fromHistory = normalizeHistoryRow({
      id: 11, sender_id: null, kind: 'quiz_question',
      content: JSON.stringify({ question_id: 12, question: 'Sual?', options: ['A', 'B'] }),
    });
    const fromLive = normalizeLiveEvent({
      type: 'quiz_question', question_id: 12, question: 'Sual?',
      options: ['A', 'B'], message_id: 11,
    });
    assert.deepEqual(fromLive.question, fromHistory.question);
    assert.equal(fromLive.id, fromHistory.id);
    assert.equal(fromLive.kind, fromHistory.kind);
  });
});

describe('upsertItem', () => {
  test('yeni elementi sona əlavə edir', () => {
    const items = upsertItem([{ id: 1 }], { id: 2, kind: 'text' });
    assert.equal(items.length, 2);
  });

  test('eyni id-li elementi ƏVƏZ edir — yenidən qoşulmada təkrarın qarşısını alır', () => {
    // Yenidən qoşulanda server tarixçəni TƏKRAR göndərir; dedupe olmasa
    // çatda hər mesaj iki dəfə görünərdi.
    const items = upsertItem([{ id: 1, text: 'köhnə' }], { id: 1, text: 'yeni' });
    assert.equal(items.length, 1);
    assert.equal(items[0].text, 'yeni');
  });

  test('null elementi siyahını dəyişmir', () => {
    const original = [{ id: 1 }];
    assert.equal(upsertItem(original, null), original);
  });

  test('orijinal siyahını dəyişdirmir (immutable)', () => {
    const original = [{ id: 1 }];
    upsertItem(original, { id: 2 });
    assert.equal(original.length, 1);
  });
});
