import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  DURATION_CHOICES_MINUTES,
  LiveHostSocket,
  LivePlaySocket,
  formatCountdown,
  participantRows,
  progressPercent,
} from '../assets/js/live.js';

describe('formatCountdown', () => {
  test('dəqiqə:saniyə formatı', () => {
    assert.equal(formatCountdown(180), '3:00');
    assert.equal(formatCountdown(65), '1:05');
    assert.equal(formatCountdown(9), '0:09');
  });

  test('mənfi vaxt 0 göstərilir', () => {
    // Vaxt bitəndən sonra "-0:03" göstərmək mənasızdır.
    assert.equal(formatCountdown(-5), '0:00');
  });

  test('yararsız dəyər sındırmır', () => {
    assert.equal(formatCountdown(null), '0:00');
    assert.equal(formatCountdown('salam'), '0:00');
  });
});

describe('progressPercent', () => {
  test('faizi hesablayır', () => {
    assert.equal(progressPercent(5, 10), 50);
  });

  test('sıfıra bölmə yoxdur', () => {
    assert.equal(progressPercent(3, 0), 0);
  });

  test('100%-dən yuxarı qalxmır', () => {
    assert.equal(progressPercent(12, 10), 100);
  });
});

describe('participantRows', () => {
  const participants = [
    { id: 1, display_name: 'Əli' },
    { id: 2, display_name: 'Nurlan' },
    { id: 3, display_name: '' },
  ];

  test('iştirakçı siyahısı ilə tərəqqi hadisələrini birləşdirir', () => {
    // İkisi AYRI gəlir: `state`/`participant_joined` vs
    // `participant_progress`.
    const rows = participantRows(participants, new Map([[1, 3], [2, 10]]), 10);
    assert.equal(rows[0].answered, 3);
    assert.equal(rows[0].percent, 30);
    assert.equal(rows[0].finished, false);
    assert.equal(rows[1].finished, true);
  });

  test('tərəqqisi gəlməmiş iştirakçı sıfırla göstərilir', () => {
    const rows = participantRows(participants, new Map(), 10);
    assert.equal(rows[2].answered, 0);
  });

  test('adsız iştirakçı üçün ehtiyat ad', () => {
    const rows = participantRows(participants, new Map(), 10);
    assert.equal(rows[2].name, 'İştirakçı #3');
  });

  test('boş siyahı sındırmır', () => {
    assert.deepEqual(participantRows(null, new Map(), 10), []);
  });
});

test('vaxt seçimləri 1-10 dəqiqə aralığındadır', () => {
  assert.ok(DURATION_CHOICES_MINUTES.every((m) => m >= 1 && m <= 10));
});

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
  receive(payload) { if (this.onmessage) this.onmessage({ data: JSON.stringify(payload) }); }
}

describe('LiveHostSocket', () => {
  test('sessiya ID-si ilə host ünvanına qoşulur', () => {
    // PIN yolu əvəzləndi: sessiya bir sinfə bağlıdır, konsol isə
    // yalnız onu başladan müəllimə açılır (server `created_by`-a baxır).
    const socket = new LiveHostSocket({
      sessionId: 42, token: 'tok', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    assert.match(FakeSocket.last.url, /\/ws\/live\/sessions\/42\/host\?token=tok$/);
    socket.close();
  });

  test('başlatma mesajı backend-in gözlədiyi açarlarla gedir', () => {
    const socket = new LiveHostSocket({
      sessionId: 1, token: 't', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    FakeSocket.last.open();
    socket.start(180);
    assert.deepEqual(FakeSocket.last.sent[0], { action: 'start', duration_seconds: 180 });
    socket.close();
  });

  test('bağlantı açıq deyilsə başlatma uğursuz olduğunu bildirir', () => {
    const socket = new LiveHostSocket({
      sessionId: 1, token: 't', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    assert.equal(socket.start(180), false);
    socket.close();
  });
});

describe('LivePlaySocket', () => {
  test('sessiya ID-si və token ilə qoşulur', () => {
    const socket = new LivePlaySocket({
      sessionId: 42, token: 'tok', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    assert.match(FakeSocket.last.url, /\/ws\/live\/sessions\/42\/play\?token=tok$/);
    socket.close();
  });

  test('qoşulanda HEÇ BİR ad mesajı göndərmir', () => {
    // Tələbə artıq ad yazmır - server onu hesabdan götürür. Köhnə
    // yolda ilk mesaj `display_name` idi; burada olmamalıdır.
    const socket = new LivePlaySocket({
      sessionId: 1, token: 'tok', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    FakeSocket.last.open();
    assert.deepEqual(FakeSocket.last.sent, []);
    socket.close();
  });

  test('cavab və növbəti mesajları düzgün formatdadır', () => {
    const socket = new LivePlaySocket({
      sessionId: 1, token: 't', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    FakeSocket.last.open();
    socket.answer(2, 3);
    socket.next();
    assert.deepEqual(FakeSocket.last.sent[0], {
      type: 'answer', question_index: 2, chosen_index: 3,
    });
    assert.deepEqual(FakeSocket.last.sent[1], { type: 'next' });
    socket.close();
  });
});
