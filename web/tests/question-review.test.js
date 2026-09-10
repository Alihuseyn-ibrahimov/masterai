import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

import {
  REVIEW_ORDER, SOURCE_ORDER,
  findingsByQuestion, orderedIndexes, setWideFindings,
  severityBadge, suspiciousCount,
} from '../assets/js/question-review.js';

const FINDINGS = [
  { code: 'tekrar_variant', severity: 'yuksek', message: 'a', question_number: 2 },
  { code: 'zeif_izah', severity: 'orta', message: 'b', question_number: 2 },
  { code: 'movqe_eyriliyi', severity: 'orta', message: 'c', question_number: null },
];

describe('tapıntıların suala görə qruplaşdırılması', () => {
  test('bir sualın bütün tapıntıları bir yerdədir', () => {
    const byQuestion = findingsByQuestion(FINDINGS);
    assert.deepEqual(byQuestion.get(2).map((f) => f.code), ['tekrar_variant', 'zeif_izah']);
  });

  test('dəstin bütününə aid tapıntı suala yazılmır', () => {
    // `question_number: null` konkret sualın problemi deyil - onu sual
    // kartına yapışdırsaq müəllim səhv sualı düzəltməyə başlayar.
    const byQuestion = findingsByQuestion(FINDINGS);
    assert.equal(byQuestion.has(null), false);
    assert.equal([...byQuestion.keys()].length, 1);
  });

  test('dəst tapıntıları ayrıca qaytarılır', () => {
    assert.deepEqual(setWideFindings(FINDINGS).map((f) => f.code), ['movqe_eyriliyi']);
  });

  test('boş siyahı sındırmır', () => {
    assert.equal(findingsByQuestion([]).size, 0);
    assert.deepEqual(setWideFindings([]), []);
    assert.deepEqual(setWideFindings(undefined), []);
  });
});

describe('şübhəli sual sayı', () => {
  test('sualları sayır, tapıntıları yox', () => {
    // 2-ci sualda İKİ tapıntı var, amma şübhəli sual BİRDİR - müəllimə
    // "2 sual yoxlanmalıdır" demək "3 tapıntı var" deməkdən faydalıdır.
    assert.equal(suspiciousCount(FINDINGS), 1);
  });

  test('yalnız dəst tapıntısı olanda sıfırdır', () => {
    assert.equal(suspiciousCount([{ code: 'x', severity: 'orta', question_number: null }]), 0);
  });
});

describe('sıralama', () => {
  test('mənbə sırası sadəcə 0..n-1', () => {
    assert.deepEqual(orderedIndexes(3, [3, 1, 2], SOURCE_ORDER), [0, 1, 2]);
  });

  test('yoxlama sırası audit sırasını 0-bazlı indeksə çevirir', () => {
    assert.deepEqual(orderedIndexes(3, [3, 1, 2], REVIEW_ORDER), [2, 0, 1]);
  });

  test('audit sırası natamam olsa qalan suallar İTMİR', () => {
    // Sual silinəndən sonra köhnə audit cavabı qısa qala bilər; heç bir
    // sual ekrandan yox olmamalıdır.
    assert.deepEqual(orderedIndexes(4, [3], REVIEW_ORDER), [2, 0, 1, 3]);
  });

  test('audit sırasında olmayan nömrə (silinmiş sual) atılır', () => {
    assert.deepEqual(orderedIndexes(2, [5, 2, 1], REVIEW_ORDER), [1, 0]);
  });

  test('audit sırası boşdursa mənbə sırası işlədilir', () => {
    assert.deepEqual(orderedIndexes(3, [], REVIEW_ORDER), [0, 1, 2]);
  });
});

describe('ciddilik nişanı', () => {
  test('üç səviyyənin hər biri öz sinfini alır', () => {
    assert.equal(severityBadge('yuksek').className, 'badge badge--danger');
    assert.equal(severityBadge('orta').className, 'badge badge--warning');
    assert.equal(severityBadge('asagi').className, 'badge badge--neutral');
  });

  test('etiket Azərbaycancadır', () => {
    assert.equal(severityBadge('yuksek').label, 'Yüksək');
    assert.equal(severityBadge('orta').label, 'Orta');
    assert.equal(severityBadge('asagi').label, 'Aşağı');
  });

  test('naməlum səviyyə rəngsiz qalmır', () => {
    assert.equal(severityBadge('kosmik').className, 'badge badge--neutral');
    assert.equal(severityBadge(undefined).label, 'Qeyd');
  });
});
