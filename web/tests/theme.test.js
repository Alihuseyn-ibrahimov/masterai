import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

import { applyTheme, readStoredTheme, setTheme, THEME_KEY } from '../assets/js/theme.js';

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: (k) => { delete data[k]; },
    _data: data,
  };
}

function fakeRoot() {
  const attrs = {};
  return {
    setAttribute: (k, v) => { attrs[k] = v; },
    removeAttribute: (k) => { delete attrs[k]; },
    getAttribute: (k) => (k in attrs ? attrs[k] : null),
  };
}

/** Yaddaşı bloklanmış brauzer (Safari gizli rejimi) - ATIR. */
function blockedStorage() {
  return {
    getItem() { throw new Error('bloklanıb'); },
    setItem() { throw new Error('bloklanıb'); },
    removeItem() { throw new Error('bloklanıb'); },
  };
}

describe('görünüş seçimi', () => {
  test('saxlanmış seçim oxunur', () => {
    assert.equal(readStoredTheme(fakeStorage({ [THEME_KEY]: 'dark' })), 'dark');
    assert.equal(readStoredTheme(fakeStorage({ [THEME_KEY]: 'light' })), 'light');
  });

  test('seçim yoxdursa cihaz seçimi qalır', () => {
    assert.equal(readStoredTheme(fakeStorage()), 'system');
  });

  test('yararsız dəyər cihaz seçiminə düşür', () => {
    // Yaddaşa kənardan düşmüş zibil ekranı sındırmamalıdır.
    assert.equal(readStoredTheme(fakeStorage({ [THEME_KEY]: 'qırmızı' })), 'system');
  });

  test('yaddaş bloklanıbsa atmır', () => {
    assert.equal(readStoredTheme(blockedStorage()), 'system');
  });

  test('tünd seçimi atribut qoyur', () => {
    const root = fakeRoot();
    applyTheme('dark', root);
    assert.equal(root.getAttribute('data-theme'), 'dark');
  });

  test('«cihaza uyğun» atributu SİLİR', () => {
    // Atribut qalsa, CSS-dəki `prefers-color-scheme` qaydası işə düşməz.
    const root = fakeRoot();
    applyTheme('dark', root);
    applyTheme('system', root);
    assert.equal(root.getAttribute('data-theme'), null);
  });

  test('setTheme həm yazır, həm tətbiq edir', () => {
    const storage = fakeStorage();
    const root = fakeRoot();
    setTheme('dark', { storage, root });
    assert.equal(storage._data[THEME_KEY], 'dark');
    assert.equal(root.getAttribute('data-theme'), 'dark');
  });

  test('«cihaza uyğun» yaddaşdan da silinir', () => {
    const storage = fakeStorage({ [THEME_KEY]: 'dark' });
    const root = fakeRoot();
    setTheme('system', { storage, root });
    assert.equal(THEME_KEY in storage._data, false);
    assert.equal(root.getAttribute('data-theme'), null);
  });

  test('yaddaş bloklanıbsa seçim YENƏ DƏ tətbiq olunur', () => {
    // İstifadəçi heç olmasa bu səhifədə nəticəni görməlidir.
    const root = fakeRoot();
    setTheme('dark', { storage: blockedStorage(), root });
    assert.equal(root.getAttribute('data-theme'), 'dark');
  });
});
