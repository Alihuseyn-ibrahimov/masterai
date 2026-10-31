import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { ReconnectingSocket, withTicket } from '../assets/js/socket.js';
import { ChatSocket } from '../assets/js/chat-socket.js';

class FakeSocket {
  constructor(url) {
    this.url = url;
    FakeSocket.all.push(this);
  }
  close() {}
}
FakeSocket.all = [];

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('WebSocket ticket', () => {
  test('hər qoşulma YENİ ticket istəyir və JWT URL-ə düşmür', async () => {
    FakeSocket.all = [];
    let n = 0;
    const socket = new ChatSocket({
      chatId: 3,
      token: 'eyJ.jwt.imza',
      getTicket: async () => `t${++n}`,
      onHistory: () => {}, onItem: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    await tick();
    socket.socket.connect();
    await tick();
    assert.deepEqual(FakeSocket.all.map((s) => s.url.split('?')[1]), ['ticket=t1', 'ticket=t2']);
    assert.ok(FakeSocket.all.every((s) => !s.url.includes('eyJ')));
    socket.close();
  });

  test('401: sessiya bitib - yenidən cəhd edilmir', async () => {
    FakeSocket.all = [];
    const statuses = [];
    const socket = new ReconnectingSocket({
      url: withTicket(() => Promise.reject(Object.assign(new Error('x'), { status: 401 })), (t) => `ws://x?ticket=${t}`),
      onMessage: () => {},
      onStatus: (s) => statuses.push(s),
      socketFactory: FakeSocket,
    });
    socket.connect();
    await tick();
    assert.equal(statuses.at(-1), 'closed');
    assert.equal(FakeSocket.all.length, 0);
    assert.equal(socket.timer, null);
  });

  test('şəbəkə xətası: gözləyib yenidən cəhd planlaşdırılır', async () => {
    const statuses = [];
    const socket = new ReconnectingSocket({
      url: withTicket(() => Promise.reject(Object.assign(new Error('x'), { status: 0 })), (t) => t),
      onMessage: () => {},
      onStatus: (s) => statuses.push(s),
      socketFactory: FakeSocket,
    });
    socket.connect();
    await tick();
    assert.equal(statuses.at(-1), 'reconnecting');
    assert.ok(socket.timer);
    socket.close();
  });

  test('bağlandıqdan sonra gələn ticket soket açmır', async () => {
    FakeSocket.all = [];
    let release;
    const socket = new ReconnectingSocket({
      url: withTicket(() => new Promise((resolve) => { release = resolve; }), (t) => `ws://x?ticket=${t}`),
      onMessage: () => {},
      socketFactory: FakeSocket,
    });
    socket.connect();
    socket.close();
    release('gec');
    await tick();
    assert.equal(FakeSocket.all.length, 0);
  });
});
