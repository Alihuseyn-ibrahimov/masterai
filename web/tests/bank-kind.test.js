/* Reading bankı yalnız ev tapşırığı üçündür (spec 2026-09-29 §5).
 * Canlı sessiya seçicisi onu GÖSTƏRMƏMƏLİDİR - server onsuz da 400
 * qaytarır, amma müəllim əvvəlcə seçib sonra xəta görməməlidir. */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { bankKindNote, isLiveEligible } from '../assets/js/bank-card.js';

describe('isLiveEligible', () => {
  test('hazır adi bank canlı sessiyaya uyğundur', () => {
    assert.equal(isLiveEligible({ status: 'ready', bank_kind: 'practice' }), true);
  });

  test('köhnə bank (bank_kind yoxdur) uyğundur', () => {
    assert.equal(isLiveEligible({ status: 'ready' }), true);
  });

  test('reading bankı uyğun deyil', () => {
    assert.equal(isLiveEligible({ status: 'ready', bank_kind: 'reading' }), false);
  });

  test('hazır olmayan bank uyğun deyil', () => {
    assert.equal(isLiveEligible({ status: 'processing', bank_kind: 'practice' }), false);
  });
});

describe('bankKindNote', () => {
  test('reading üçün qeyd', () => {
    assert.match(bankKindNote({ bank_kind: 'reading' }), /Reading/);
    assert.match(bankKindNote({ bank_kind: 'reading' }), /ev tapşırığı/);
  });

  test('adi bank üçün qeyd yoxdur', () => {
    assert.equal(bankKindNote({ bank_kind: 'practice' }), '');
    assert.equal(bankKindNote({}), '');
  });
});
