import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

import { historySummary } from '../assets/js/history.js';

const entry = (subject, score, total) => ({
  kind: 'homework', subject, title: 't', score, total_questions: total, date: '2026-09-01',
});

describe('tarixçə xülasəsi', () => {
  test('boş tarixçə sındırmır', () => {
    const s = historySummary([]);
    assert.equal(s.count, 0);
    assert.equal(s.percent, null);
    assert.equal(s.weakest, null);
  });

  test('ümumi faiz BÜTÜN suallar üzrə hesablanır', () => {
    // Nəticələrin faizlərinin ortası DEYİL: 10 suallıq test 2 suallıqdan
    // çox çəkməlidir.
    const s = historySummary([entry('mentiq', 10, 10), entry('mentiq', 0, 2)]);
    assert.equal(s.count, 2);
    assert.equal(s.score, 10);
    assert.equal(s.total, 12);
    assert.equal(s.percent, 83);
  });

  test('fənn üzrə bölgü zəifdən başlayır', () => {
    const s = historySummary([
      entry('mentiq', 9, 10), entry('mentiq', 9, 10),
      entry('informatika', 4, 10), entry('informatika', 4, 10),
    ]);
    assert.deepEqual(s.bySubject.map((row) => row.subject), ['informatika', 'mentiq']);
    assert.equal(s.bySubject[0].percent, 40);
  });

  test('zəif fənn yalnız KİFAYƏT QƏDƏR data olanda deyilir', () => {
    // Bir dəfəlik pis nəticə "zəif fənn" deyil - tələbəni yanlış
    // yönləndirmək faydadan pisdir.
    const s = historySummary([entry('mentiq', 9, 10), entry('informatika', 0, 3)]);
    assert.equal(s.weakest, null);
  });

  test('zəif fənn ancaq ümumidən nəzərəçarpacaq aşağıdırsa deyilir', () => {
    const s = historySummary([
      entry('mentiq', 8, 10), entry('mentiq', 8, 10),
      entry('informatika', 7, 10), entry('informatika', 8, 10),
    ]);
    assert.equal(s.weakest, null, 'fərq kiçikdir - zəif fənn elan edilməməlidir');
  });

  test('həqiqi zəif fənn tapılır', () => {
    const s = historySummary([
      entry('mentiq', 10, 10), entry('mentiq', 9, 10),
      entry('informatika', 3, 10), entry('informatika', 4, 10),
    ]);
    assert.equal(s.weakest.subject, 'informatika');
    assert.equal(s.weakest.percent, 35);
  });

  test('tək fənn varsa müqayisə mənasızdır', () => {
    const s = historySummary([entry('mentiq', 1, 10), entry('mentiq', 2, 10)]);
    assert.equal(s.weakest, null);
  });

  test('sıfır suallı sətir bölməni sındırmır', () => {
    const s = historySummary([entry('mentiq', 0, 0)]);
    assert.equal(s.percent, null);
    assert.equal(s.count, 1);
  });
});
