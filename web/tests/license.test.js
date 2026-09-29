/* Lisenziya qapısının client tərəfi.
 *
 * Server bağlı kursa HTTP 402 və WS 4402 qaytarır (spec 2026-09-29 §2).
 * Client hər ikisində EYNİ «abunə bitib» səhifəsinə keçməlidir; 4402
 * FATAL olmalıdır - əks halda `ReconnectingSocket` sonsuz yenidən
 * qoşulur və tələbə spinnerə baxıb qalır.
 */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  CLOSED_PAGE,
  expiryBannerText,
  goToClosedPage,
  shouldShowExpiryBanner,
} from '../assets/js/license.js';
import { request, saveSession } from '../assets/js/api.js';
import { isFatalCloseCode, ReconnectingSocket } from '../assets/js/socket.js';

function fakeLocation(pathname = '/chatlar.html') {
  const calls = [];
  return { pathname, calls, replace: (url) => calls.push(url) };
}

function withLocation(loc, fn) {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'location');
  Object.defineProperty(globalThis, 'location', { value: loc, configurable: true, writable: true });
  const restore = () => {
    if (original) Object.defineProperty(globalThis, 'location', original);
    else delete globalThis.location;
  };
  let result;
  try {
    result = fn();
  } catch (error) {
    restore();
    throw error;
  }
  if (result && typeof result.then === 'function') return result.finally(restore);
  restore();
  return result;
}

describe('goToClosedPage', () => {
  test('bağlı səhifəyə yönləndirir', () => {
    const loc = fakeLocation();
    goToClosedPage(loc);
    assert.deepEqual(loc.calls, [CLOSED_PAGE]);
  });

  test('artıq bağlı səhifədədirsə döngü yaratmır', () => {
    const loc = fakeLocation(`/${CLOSED_PAGE}`);
    goToClosedPage(loc);
    assert.deepEqual(loc.calls, []);
  });

  test('location olmayan mühitdə (Node) atmır', () => {
    assert.doesNotThrow(() => goToClosedPage(undefined));
  });
});

describe('shouldShowExpiryBanner', () => {
  const teacher = { is_teacher: true };
  const student = { is_teacher: false };

  test('müəllimə 5 gün və az qalanda göstərilir', () => {
    assert.equal(shouldShowExpiryBanner(teacher, { days_left: 5 }), true);
    assert.equal(shouldShowExpiryBanner(teacher, { days_left: 1 }), true);
  });

  test('6 gün qalanda göstərilmir', () => {
    assert.equal(shouldShowExpiryBanner(teacher, { days_left: 6 }), false);
  });

  test('tələbəyə heç vaxt göstərilmir', () => {
    assert.equal(shouldShowExpiryBanner(student, { days_left: 2 }), false);
  });

  test('müddətsiz (owner) kurs üçün göstərilmir', () => {
    assert.equal(shouldShowExpiryBanner(teacher, { days_left: null }), false);
  });

  test('məlumat yoxdursa göstərilmir', () => {
    assert.equal(shouldShowExpiryBanner(null, { days_left: 2 }), false);
    assert.equal(shouldShowExpiryBanner(teacher, null), false);
  });
});

describe('expiryBannerText', () => {
  test('gün sayını deyir', () => {
    assert.match(expiryBannerText(3), /3 gün/);
  });

  test('son gün üçün ayrıca mətn', () => {
    assert.match(expiryBannerText(1), /bu gün|sabah|1 gün/);
  });
});

describe('api.request 402', () => {
  test('402 cavabında bağlı səhifəyə keçir və xəta atır', async () => {
    saveSession({ token: 't', user: { id: 1 } });
    const loc = fakeLocation();
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ detail: 'Kursunuzun abunəsi bitib.' }), { status: 402 });
    try {
      await withLocation(loc, () =>
        assert.rejects(() => request('/chats'), (err) => err.status === 402),
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
    assert.deepEqual(loc.calls, [CLOSED_PAGE]);
  });

  test('digər xətalarda yönləndirmir', async () => {
    const loc = fakeLocation();
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => new Response('{}', { status: 403 });
    try {
      await withLocation(loc, () => assert.rejects(() => request('/chats')));
    } finally {
      globalThis.fetch = originalFetch;
    }
    assert.deepEqual(loc.calls, []);
  });
});

describe('WebSocket 4402', () => {
  test('4402 fatal koddur (yenidən qoşulma yoxdur)', () => {
    assert.equal(isFatalCloseCode(4402), true);
  });

  test('4402 ilə bağlananda bağlı səhifəyə keçir', () => {
    const loc = fakeLocation();
    let created = null;
    class FakeSocket {
      constructor() { created = this; }
      close() {}
    }
    const statuses = [];
    const socket = new ReconnectingSocket({
      url: () => 'ws://x',
      onMessage: () => {},
      onStatus: (s) => statuses.push(s),
      socketFactory: FakeSocket,
    });
    withLocation(loc, () => {
      socket.connect();
      created.onclose({ code: 4402 });
    });
    assert.deepEqual(loc.calls, [CLOSED_PAGE]);
    assert.equal(statuses.at(-1), 'closed');
  });
});
