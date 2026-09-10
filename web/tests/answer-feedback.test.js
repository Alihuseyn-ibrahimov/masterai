import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

import { answerFeedback, scoreLine } from '../assets/js/answer-feedback.js';

const OPTIONS = ['Elmi fəaliyyət', 'Sahibkarlıq', 'Pedaqoji fəaliyyət', 'Yaradıcılıq', 'Tədris'];

describe('cavab geri bildirimi', () => {
  test('düzgün cavab MƏTNİ ilə göstərilir', () => {
    // Yalnız "Düzgün cavab: B" yazmaq heç nə öyrətmir: variantlar artıq
    // ekranda deyil, tələbə B-nin nə olduğunu xatırlamır.
    const f = answerFeedback({ options: OPTIONS, correctIndex: 1, chosenIndex: 3, isCorrect: false });
    assert.equal(f.correctLine, 'Düzgün cavab: B. Sahibkarlıq');
  });

  test('səhv cavabda tələbənin seçimi də yazılır', () => {
    const f = answerFeedback({ options: OPTIONS, correctIndex: 1, chosenIndex: 3, isCorrect: false });
    assert.equal(f.chosenLine, 'Sizin cavabınız: D. Yaradıcılıq');
  });

  test('düzgün cavabda seçim sətri təkrarlanmır', () => {
    const f = answerFeedback({ options: OPTIONS, correctIndex: 1, chosenIndex: 1, isCorrect: true });
    assert.equal(f.chosenLine, null);
    assert.equal(f.badge.label, 'Düzgün');
    assert.equal(f.badge.className, 'badge badge--success');
  });

  test('səhv nişanı', () => {
    const f = answerFeedback({ options: OPTIONS, correctIndex: 0, chosenIndex: 2, isCorrect: false });
    assert.equal(f.badge.label, 'Səhv');
    assert.equal(f.badge.className, 'badge badge--danger');
  });

  test('variantlar əlçatan deyilsə hərf yenə göstərilir', () => {
    // Canlı sessiyada mesaj gecikə bilər; ekran boş qalmamalıdır.
    const f = answerFeedback({ options: null, correctIndex: 2, chosenIndex: 0, isCorrect: false });
    assert.equal(f.correctLine, 'Düzgün cavab: C');
    assert.equal(f.chosenLine, 'Sizin cavabınız: A');
  });

  test('indeks sərhəddən kənardırsa sındırmır', () => {
    const f = answerFeedback({ options: OPTIONS, correctIndex: 9, chosenIndex: null, isCorrect: false });
    assert.equal(f.correctLine, 'Düzgün cavab: -');
    assert.equal(f.chosenLine, null);
  });
});

describe('yekun nəticə sətri', () => {
  test('məxrəc və faiz', () => {
    assert.equal(scoreLine(8, 10), '8/10 düzgün cavab (80%)');
  });

  test('tam nəticə', () => {
    assert.equal(scoreLine(5, 5), '5/5 düzgün cavab (100%)');
  });

  test('ümumi say bilinmirsə faiz uydurulmur', () => {
    assert.equal(scoreLine(3, 0), '3 düzgün cavab');
    assert.equal(scoreLine(3, null), '3 düzgün cavab');
  });
});
