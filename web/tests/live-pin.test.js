import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  LivePinPlaySocket, guestKey, isValidPin, joinLink, normalizePin,
} from '../assets/js/live-pin.js';

class FakeSocket {
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.sent = [];
    FakeSocket.last = this;
  }
  send(data) { this.sent.push(JSON.parse(data)); }
  close() { this.readyState = 3; }
  open() { this.readyState = 1; if (this.onopen) this.onopen(); }
}

class MemoryStorage {
  constructor() { this.data = new Map(); }
  getItem(k) { return this.data.has(k) ? this.data.get(k) : null; }
  setItem(k, v) { this.data.set(k, String(v)); }
}

const fakeCrypto = { getRandomValues: (arr) => { arr.fill(7); return arr; } };

describe('PIN formatı', () => {
  test('boşluq və tire təmizlənir', () => {
    assert.equal(normalizePin(' 123 456 '), '123456');
    assert.equal(normalizePin('12-34-56'), '123456');
  });

  test('yalnız 6 rəqəm keçərlidir', () => {
    assert.ok(isValidPin('012345'));
    assert.ok(!isValidPin('12345'));
    assert.ok(!isValidPin('1234567'));
    assert.ok(!isValidPin('abcdef'));
  });

  test('link PIN-i daşıyır', () => {
    assert.equal(joinLink('012345', 'https://masterai.prdostu.com'),
      'https://masterai.prdostu.com/qosul.html?pin=012345');
  });
});

describe('guestKey', () => {
  test('eyni PIN üçün eyni açar qaytarır (yeniləmə yeni sətir yaratmır)', () => {
    const storage = new MemoryStorage();
    const first = guestKey('123456', { storage, cryptoImpl: fakeCrypto });
    const second = guestKey('123456', { storage, cryptoImpl: { getRandomValues: () => { throw new Error('çağırılmamalı'); } } });
    assert.equal(first, second);
    assert.match(first, /^[0-9a-f]{24}$/);
  });

  test('bloklanmış yaddaş qoşulmanı sındırmır', () => {
    const blocked = { getItem() { throw new Error('blok'); }, setItem() { throw new Error('blok'); } };
    assert.match(guestKey('123456', { storage: blocked, cryptoImpl: fakeCrypto }), /^[0-9a-f]{24}$/);
  });
});

describe('LivePinPlaySocket', () => {
  test('PIN, ad və açarla qonaq ünvanına qoşulur, tokensiz', () => {
    const socket = new LivePinPlaySocket({
      pin: '123456', name: 'Aysel Ə', guest: 'acar1234', token: '',
      onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    assert.match(FakeSocket.last.url, /\/ws\/live\/pin\/123456\/play\?name=Aysel%20%C6%8F&guest=acar1234$/);
    socket.close();
  });

  test('token varsa əlavə olunur', () => {
    const socket = new LivePinPlaySocket({
      pin: '123456', name: 'A', guest: 'acar1234', token: 'tok',
      onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    assert.match(FakeSocket.last.url, /&token=tok$/);
    socket.close();
  });

  test('cavab mesajı formatı', () => {
    const socket = new LivePinPlaySocket({
      pin: '123456', name: 'A', guest: 'acar1234', token: '',
      onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    FakeSocket.last.open();
    socket.answer(2, 4);
    socket.next();
    assert.deepEqual(FakeSocket.last.sent, [
      { type: 'answer', question_index: 2, chosen_index: 4 },
      { type: 'next' },
    ]);
    socket.close();
  });
});
