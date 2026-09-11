import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { ChatSocket, computeBackoffDelay, isFatalCloseCode } from '../assets/js/chat-socket.js';

describe('isFatalCloseCode', () => {
  test('serverin rədd kodlarında yenidən qoşulmur', () => {
    // `chat_websocket` bu kodları qaytarır: 4401 token, 4403 üzv deyil,
    // 4404 çat yoxdur. Onlarda təkrar cəhd serveri boş yerə yükləyər.
    assert.equal(isFatalCloseCode(4401), true);
    assert.equal(isFatalCloseCode(4403), true);
    assert.equal(isFatalCloseCode(4404), true);
  });

  test('adi kəsilmələrdə yenidən qoşulur', () => {
    assert.equal(isFatalCloseCode(1006), false); // anormal kəsilmə
    assert.equal(isFatalCloseCode(1001), false); // səhifə bağlandı
    assert.equal(isFatalCloseCode(undefined), false);
  });
});

describe('computeBackoffDelay', () => {
  test('cəhd artdıqca gözləmə artır', () => {
    const fixed = () => 0.5;
    assert.ok(computeBackoffDelay(0, fixed) < computeBackoffDelay(1, fixed));
    assert.ok(computeBackoffDelay(1, fixed) < computeBackoffDelay(2, fixed));
  });

  test('üst hədd aşılmır', () => {
    assert.ok(computeBackoffDelay(50, () => 1) <= 30000);
  });

  test('jitter var — eyni cəhd fərqli dəyər verə bilir', () => {
    // Eyni anda kəsilən çoxlu client serverə eyni saniyədə qayıtmamalıdır.
    assert.notEqual(computeBackoffDelay(3, () => 0), computeBackoffDelay(3, () => 1));
  });

  test('mənfi cəhd nömrəsi sındırmır', () => {
    assert.ok(computeBackoffDelay(-5, () => 0.5) > 0);
  });
});

/** Real WebSocket-i əvəz edən minimal saxta obyekt. */
class FakeSocket {
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.sent = [];
    FakeSocket.last = this;
  }
  send(data) { this.sent.push(data); }
  close() { this.readyState = 3; }
  open() { this.readyState = 1; if (this.onopen) this.onopen(); }
  receive(payload) { if (this.onmessage) this.onmessage({ data: JSON.stringify(payload) }); }
}

describe('ChatSocket', () => {
  function build(overrides = {}) {
    const received = { history: null, items: [], errors: [], statuses: [] };
    const socket = new ChatSocket({
      chatId: 7,
      token: 'tok en/with+special',
      onHistory: (items) => { received.history = items; },
      onItem: (item) => received.items.push(item),
      onServerError: (detail) => received.errors.push(detail),
      onStatus: (status) => received.statuses.push(status),
      socketFactory: FakeSocket,
      ...overrides,
    });
    return { socket, received };
  }

  test('URL-də token kodlaşdırılır', () => {
    const { socket } = build();
    socket.connect();
    assert.match(FakeSocket.last.url, /\/ws\/chat\/7\?token=/);
    // Xüsusi simvollar xam getsə server tokeni səhv oxuyar.
    assert.ok(!FakeSocket.last.url.includes(' '));
    assert.ok(FakeSocket.last.url.includes('%20'));
    socket.close();
  });

  test('tarixçəni normallaşdırılmış şəkildə verir', () => {
    const { socket, received } = build();
    socket.connect();
    FakeSocket.last.receive({
      type: 'history',
      messages: [{ id: 1, kind: 'text', sender_id: 2, content: 'Salam' }],
    });
    assert.equal(received.history.length, 1);
    assert.equal(received.history[0].text, 'Salam');
    socket.close();
  });

  test('canlı hadisəni element kimi verir', () => {
    const { socket, received } = build();
    socket.connect();
    FakeSocket.last.receive({
      type: 'quiz_question', question_id: 3, question: 'Sual?', options: ['A'], message_id: 9,
    });
    assert.equal(received.items.length, 1);
    assert.equal(received.items[0].id, 9);
    socket.close();
  });

  test('server xətasını ayrıca verir, element kimi yox', () => {
    const { socket, received } = build();
    socket.connect();
    FakeSocket.last.receive({ type: 'error', detail: 'mesaj formatı düzgün deyil' });
    assert.deepEqual(received.errors, ['mesaj formatı düzgün deyil']);
    assert.equal(received.items.length, 0);
    socket.close();
  });

  test('oxunmayan çərçivə bağlantını sındırmır', () => {
    const { socket } = build();
    socket.connect();
    assert.doesNotThrow(() => FakeSocket.last.onmessage({ data: '{yarımçıq' }));
    socket.close();
  });

  test('bağlantı açıq deyilsə göndərmə uğursuz olduğunu bildirir', () => {
    const { socket } = build();
    socket.connect();
    // readyState hələ 0 — istifadəçi mesajı "getdi" sanmamalıdır.
    assert.equal(socket.sendText('salam'), false);
    FakeSocket.last.open();
    assert.equal(socket.sendText('salam'), true);
    assert.equal(JSON.parse(FakeSocket.last.sent[0]).content, 'salam');
    socket.close();
  });

  test('cavab mesajı backend-in gözlədiyi açarlarla gedir', () => {
    const { socket } = build();
    socket.connect();
    FakeSocket.last.open();
    socket.sendAnswer(12, 2);
    // `chat_websocket` `question_id` və `chosen_index` gözləyir.
    assert.deepEqual(JSON.parse(FakeSocket.last.sent[0]), {
      type: 'answer', question_id: 12, chosen_index: 2,
    });
    socket.close();
  });

  test('fatal kodda yenidən qoşulmur', () => {
    const { socket, received } = build();
    socket.connect();
    const first = FakeSocket.last;
    first.onclose({ code: 4403 });
    assert.equal(FakeSocket.last, first, 'yeni bağlantı yaradılmamalıdır');
    assert.equal(received.statuses.at(-1), 'closed');
    socket.close();
  });

  test('close() sonrası yenidən qoşulmur', () => {
    const { socket } = build();
    socket.connect();
    const first = FakeSocket.last;
    socket.close();
    first.onclose({ code: 1006 });
    assert.equal(FakeSocket.last, first);
  });
});

describe('canlı sessiya elanı', () => {
  test('`live_session` mesajı ayrıca ötürücüyə gedir', () => {
    // Kart mesaj axınında YOX, çatın yuxarısında görünür.
    const seen = [];
    const socket = new ChatSocket({
      chatId: 7, token: 't', socketFactory: FakeSocket,
      onHistory: () => {}, onItem: () => {},
      onLiveSession: (data) => seen.push(data),
    });
    socket.connect();
    FakeSocket.last.open();
    FakeSocket.last.receive({ type: 'live_session', session_id: 5, title: 'Silloqizmlər' });

    assert.equal(seen.length, 1);
    assert.equal(seen[0].session_id, 5);
    socket.close();
  });

  test('elan mesaj axınına DÜŞMÜR', () => {
    // Əks halda çatda «tanınmayan element» kimi görünə bilərdi.
    const items = [];
    const socket = new ChatSocket({
      chatId: 7, token: 't', socketFactory: FakeSocket,
      onHistory: () => {}, onItem: (item) => items.push(item),
      onLiveSession: () => {},
    });
    socket.connect();
    FakeSocket.last.open();
    FakeSocket.last.receive({ type: 'live_session', session_id: 5 });

    assert.deepEqual(items, []);
    socket.close();
  });

  test('ötürücü verilməyibsə sınmır', () => {
    // `chat.html`-dən başqa çağıran bu açarı verməyə bilər.
    const socket = new ChatSocket({
      chatId: 7, token: 't', socketFactory: FakeSocket,
      onHistory: () => {}, onItem: () => {},
    });
    socket.connect();
    FakeSocket.last.open();
    FakeSocket.last.receive({ type: 'live_session', session_id: 5 });
    socket.close();
  });
});
