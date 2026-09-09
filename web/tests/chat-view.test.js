import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  answeredQuestionIds,
  buildNameLookup,
  displayNameFor,
  formatTime,
  scoreboardRows,
} from '../assets/js/chat-view.js';

describe('buildNameLookup / displayNameFor', () => {
  const lookup = buildNameLookup([
    { user_id: 3, display_name: 'Əli Məmmədov' },
    { user_id: 7, display_name: 'Nurlan' },
  ]);

  test('real adı göstərir — Flutter-dəki "İstifadəçi #3" məhdudiyyətinin həlli', () => {
    assert.equal(displayNameFor(lookup, 3, 99), 'Əli Məmmədov');
  });

  test('öz mesajını "Siz" kimi göstərir', () => {
    assert.equal(displayNameFor(lookup, 7, 7), 'Siz');
  });

  test('ad tapılmasa köhnə davranışa geri dönür', () => {
    assert.equal(displayNameFor(lookup, 42, 7), 'İstifadəçi #42');
  });

  test('sistem mesajının göndərəni yoxdur', () => {
    assert.equal(displayNameFor(lookup, null, 7), 'Sistem');
  });

  test('etibarsız üzv siyahısı sındırmır', () => {
    assert.equal(buildNameLookup(null).size, 0);
    assert.equal(buildNameLookup([null, { user_id: 'x' }]).size, 0);
  });
});

describe('formatTime', () => {
  test('saat:dəqiqə qaytarır', () => {
    assert.match(formatTime('2026-09-09T14:05:00'), /^\d{2}:\d{2}$/);
  });

  test('yararsız dəyərdə "Invalid Date" GÖSTƏRMİR', () => {
    assert.equal(formatTime('filan-filan'), '');
    assert.equal(formatTime(null), '');
    assert.equal(formatTime(undefined), '');
  });
});

describe('scoreboardRows', () => {
  const lookup = buildNameLookup([
    { user_id: 3, display_name: 'Əli' },
    { user_id: 7, display_name: 'Nurlan' },
  ]);

  test('çoxdan aza sıralayır', () => {
    // `scores` açarları JSON-dan gəldiyi üçün SƏTİRDİR — rəqəmə
    // çevrilməsə ad axtarışı işləməz.
    const rows = scoreboardRows({ totalQuestions: 5, scores: { 3: 2, 7: 5 } }, lookup, 3);
    assert.equal(rows[0].name, 'Nurlan');
    assert.equal(rows[0].score, 5);
    assert.equal(rows[1].name, 'Siz');
  });

  test('bərabər xalda ada görə sıralayır (sabit nəticə)', () => {
    const rows = scoreboardRows({ scores: { 3: 4, 7: 4 } }, lookup, 99);
    assert.deepEqual(rows.map((row) => row.name), ['Əli', 'Nurlan']);
  });

  test('boş/yararsız girişdə boş siyahı', () => {
    assert.deepEqual(scoreboardRows(null, lookup, 1), []);
    assert.deepEqual(scoreboardRows({}, lookup, 1), []);
  });
});

describe('answeredQuestionIds', () => {
  test('nəticəsi gəlmiş sualları tanıyır', () => {
    // Real Flutter bug-ı: çat yenidən açılanda cavablanmış sual kartı
    // aktiv qalırdı, toxunanda backend "artıq cavablanıb" xətası verirdi.
    const answered = answeredQuestionIds([
      { kind: 'quiz_question', question: { questionId: 1 } },
      { kind: 'quiz_result', result: { questionId: 1 } },
      { kind: 'quiz_question', question: { questionId: 2 } },
    ]);
    assert.equal(answered.has(1), true);
    assert.equal(answered.has(2), false);
  });

  test('nəticəsi olmayan siyahıda boş çoxluq', () => {
    assert.equal(answeredQuestionIds([{ kind: 'text' }]).size, 0);
  });
});
