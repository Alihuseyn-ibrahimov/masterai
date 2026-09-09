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
  test('host ünvanına token ilə qoşulur', () => {
    const socket = new LiveHostSocket({
      pin: '123456', token: 'tok', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    assert.match(FakeSocket.last.url, /\/ws\/live\/123456\/host\?token=tok$/);
    socket.close();
  });

  test('başlatma mesajı backend-in gözlədiyi açarlarla gedir', () => {
    const socket = new LiveHostSocket({
      pin: '1', token: 't', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    FakeSocket.last.open();
    socket.start(180);
    assert.deepEqual(FakeSocket.last.sent[0], { action: 'start', duration_seconds: 180 });
    socket.close();
  });

  test('bağlantı açıq deyilsə başlatma uğursuz olduğunu bildirir', () => {
    const socket = new LiveHostSocket({
      pin: '1', token: 't', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    assert.equal(socket.start(180), false);
    socket.close();
  });
});

describe('LivePlaySocket', () => {
  test('qoşulan kimi adı İLK mesaj kimi göndərir', () => {
    // Server `display_name` gəlməsə bağlantını 4400 ilə bağlayır.
    const socket = new LivePlaySocket({
      pin: '123456', displayName: 'Əli', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    FakeSocket.last.open();
    assert.deepEqual(FakeSocket.last.sent[0], { display_name: 'Əli' });
    socket.close();
  });

  test('token verilibsə qoşulma mesajına əlavə olunur', () => {
    const socket = new LivePlaySocket({
      pin: '1', displayName: 'Əli', token: 'tok', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    FakeSocket.last.open();
    assert.deepEqual(FakeSocket.last.sent[0], { display_name: 'Əli', token: 'tok' });
    socket.close();
  });

  test('tokensiz qoşulma mesajında `token` açarı ÜMUMİYYƏTLƏ olmur', () => {
    // Boş sətir göndərsək server onu doğrulamağa çalışardı.
    const socket = new LivePlaySocket({
      pin: '1', displayName: 'Əli', token: '', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    FakeSocket.last.open();
    assert.equal('token' in FakeSocket.last.sent[0], false);
    socket.close();
  });

  test('cavab və növbəti mesajları düzgün formatdadır', () => {
    const socket = new LivePlaySocket({
      pin: '1', displayName: 'Ə', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    FakeSocket.last.open();
    socket.answer(2, 3);
    socket.next();
    assert.deepEqual(FakeSocket.last.sent[1], {
      type: 'answer', question_index: 2, chosen_index: 3,
    });
    assert.deepEqual(FakeSocket.last.sent[2], { type: 'next' });
    socket.close();
  });

  test('yenidən qoşulanda ad TƏKRAR göndərilir', () => {
    // Server hər yeni bağlantıda qoşulma mesajı gözləyir — göndərilməsə
    // bağlantı dərhal bağlanar.
    const socket = new LivePlaySocket({
      pin: '1', displayName: 'Ə', onMessage: () => {}, socketFactory: FakeSocket,
    });
    socket.connect();
    FakeSocket.last.open();
    assert.equal(FakeSocket.last.sent.length, 1);
    FakeSocket.last.open(); // yenidən açılma simulyasiyası
    assert.equal(FakeSocket.last.sent.length, 2);
    socket.close();
  });
});
