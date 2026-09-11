import assert from 'node:assert/strict';
import { test, describe } from 'node:test';

import {
  CODE_ALPHABET,
  CODE_LENGTH,
  formatCode,
  isCompleteCode,
  normalizeCode,
} from '../assets/js/invite-code.js';

describe('əlifba serverlə eynidir', () => {
  test('oxşar simvollar yoxdur', () => {
    // Server tərəfdəki eyni qayda: `0/O` və `1/I/L` qarışdırılır.
    for (const char of '0O1IL') {
      assert.ok(!CODE_ALPHABET.includes(char), `${char} əlifbada olmamalıdır`);
    }
  });

  test('uzunluq 6-dır', () => {
    assert.equal(CODE_LENGTH, 6);
  });

  test('əlifbada təkrar yoxdur', () => {
    assert.equal(new Set(CODE_ALPHABET).size, CODE_ALPHABET.length);
  });
});

describe('normalizeCode', () => {
  test('kiçik hərfi böyüdür', () => {
    assert.equal(normalizeCode('k7m3qx'), 'K7M3QX');
  });

  test('defisi atır', () => {
    assert.equal(normalizeCode('K7M-3QX'), 'K7M3QX');
  });

  test('boşluqları atır', () => {
    assert.equal(normalizeCode('  K7M 3QX '), 'K7M3QX');
  });

  test('əlifbada olmayan simvolu atır', () => {
    // `O` və `0` qəsdən əlifbada yoxdur - avtomatik əvəzləmə səhv
    // çat tapa bilərdi, ona görə sadəcə düşür.
    assert.equal(normalizeCode('KO7M3QX'), 'K7M3QX');
  });

  test('uzun girişi kəsir', () => {
    assert.equal(normalizeCode('K7M3QXZZZZ'), 'K7M3QX');
  });

  test('sətir olmayan giriş boş qaytarır', () => {
    // Forma dəyəri həmişə sətirdir, amma modul başqa yerdən də
    // çağırıla bilər - `undefined.toUpperCase()` atmamalıdır.
    assert.equal(normalizeCode(undefined), '');
    assert.equal(normalizeCode(null), '');
    assert.equal(normalizeCode(123456), '');
  });
});

describe('formatCode', () => {
  test('iki qrupa bölür', () => {
    assert.equal(formatCode('K7M3QX'), 'K7M-3QX');
  });

  test('natamam kodda da işləyir', () => {
    // İstifadəçi YAZARKƏN çağırılır - hər hərfdən sonra.
    assert.equal(formatCode('K7'), 'K7');
    assert.equal(formatCode('K7M'), 'K7M');
    assert.equal(formatCode('K7M3'), 'K7M-3');
  });

  test('artıq formatlanmış kodu təkrar bölmür', () => {
    assert.equal(formatCode('K7M-3QX'), 'K7M-3QX');
  });

  test('boş giriş boş qalır', () => {
    assert.equal(formatCode(''), '');
  });
});

describe('isCompleteCode', () => {
  test('tam kod', () => {
    assert.equal(isCompleteCode('K7M-3QX'), true);
  });

  test('natamam kod', () => {
    assert.equal(isCompleteCode('K7M3Q'), false);
  });

  test('yalnız defis', () => {
    assert.equal(isCompleteCode('------'), false);
  });
});
