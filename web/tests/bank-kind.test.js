/* Reading bankı yalnız ev tapşırığı üçündür (spec 2026-09-29 §5).
 * Canlı sessiya seçicisi onu GÖSTƏRMƏMƏLİDİR - server onsuz da 400
 * qaytarır, amma müəllim əvvəlcə seçib sonra xəta görməməlidir. */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { bankKindNote, isLiveEligible } from '../assets/js/bank-card.js';

describe('isLiveEligible', () => {
  test('hazır adi bank canlı sessiyaya uyğundur', () => {
    assert.equal(isLiveEligible({ status: 'ready', bank_kind: 'practice', question_count: 5 }), true);
  });

  test('köhnə bank (bank_kind yoxdur) uyğundur', () => {
    assert.equal(isLiveEligible({ status: 'ready', question_count: 5 }), true);
  });

  test('reading bankı uyğun deyil', () => {
    assert.equal(isLiveEligible({ status: 'ready', bank_kind: 'reading', question_count: 5 }), false);
  });

  test('hazır olmayan bank uyğun deyil', () => {
    assert.equal(isLiveEligible({ status: 'processing', bank_kind: 'practice', question_count: 5 }), false);
  });

  // Quiz olmadan konspekt (2026-11-03): sualı olmayan bank sessiyaya uyğun deyil.
  test('sualsız bank (quiz olmadan konspekt) uyğun deyil', () => {
    assert.equal(isLiveEligible({ status: 'ready', bank_kind: 'practice', question_count: 0 }), false);
  });
});

describe('bankKindNote', () => {
  test('reading üçün qeyd', () => {
    assert.match(bankKindNote({ bank_kind: 'reading' }), /Reading/);
    assert.match(bankKindNote({ bank_kind: 'reading' }), /ev tapşırığı/);
  });

  test('adi bank üçün qeyd yoxdur', () => {
    assert.equal(bankKindNote({ bank_kind: 'practice', status: 'ready', question_count: 5 }), '');
    assert.equal(bankKindNote({}), '');
  });

  test('sualsız (quiz olmadan konspekt) bank üçün qeyd', () => {
    assert.match(bankKindNote({ bank_kind: 'practice', status: 'ready', question_count: 0 }), /Yalnız xülasə/);
  });
});
