import test from 'node:test';
import assert from 'node:assert/strict';
import { rememberNext, safeNextPath, takeNext } from '../assets/js/next-path.js';

function memory() {
  const map = new Map();
  return { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, v), removeItem: (k) => map.delete(k) };
}

test('saytın öz səhifəsi qəbul olunur', () => {
  assert.equal(safeNextPath('/dersim.html?id=5&qr=ABCDE'), 'dersim.html?id=5&qr=ABCDE');
  assert.equal(safeNextPath('dersler.html'), 'dersler.html');
});

test('başqa domen və qəribə yollar rədd olunur', () => {
  for (const bad of ['https://pis.az/x.html', '//pis.az/x.html', 'javascript:alert(1)', '../x.html',
    'a/b.html', 'giris.html#x', '', null, undefined, 5]) {
    assert.equal(safeNextPath(bad), null, String(bad));
  }
});

test('qayıdış bir dəfəlikdir', () => {
  const s = memory();
  rememberNext(s, '/dersim.html?id=1&qr=X');
  assert.equal(takeNext(s), 'dersim.html?id=1&qr=X');
  assert.equal(takeNext(s), null);
});

test('təhlükəli yol yadda saxlanmır, bloklanmış yaddaş xəta atmır', () => {
  const s = memory();
  rememberNext(s, 'https://pis.az/');
  assert.equal(takeNext(s), null);
  const blocked = { getItem() { throw new Error('x'); }, setItem() { throw new Error('x'); }, removeItem() {} };
  rememberNext(blocked, 'dersim.html');
  assert.equal(takeNext(blocked), null);
});
