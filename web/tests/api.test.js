/* API client-inin vahid testləri — Node-un daxili test qoşucusu ilə
 * (`node --test`). npm quraşdırma YOXDUR.
 *
 * Bu, veb-first keçidinin konkret qazancıdır: Flutter kodunu bu
 * mühitdə ÜMUMİYYƏTLƏ icra etmək mümkün deyildi (SDK yoxdur), frontend
 * məntiqi yalnız istifadəçinin öz kompüterində yoxlanılırdı. */

import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

import {
  ApiError,
  clearSession,
  extractErrorMessage,
  getToken,
  getUser,
  isLoggedIn,
  login,
  register,
  request,
  saveSession,
} from '../assets/js/api.js';

/** Node-da `localStorage` yoxdur — client-in yaddaş ehtiyatı (memory
 *  fallback) işə düşür. Bu, sadəcə test rahatlığı deyil: eyni yol
 *  Safari-nin gizli rejimində real istifadəçilər üçün işləyir. */
beforeEach(() => clearSession());

describe('extractErrorMessage', () => {
  test('backend-in Azərbaycan dilli mesajını olduğu kimi göstərir', () => {
    assert.equal(
      extractErrorMessage(401, { detail: 'E-poçt və ya şifrə səhvdir' }),
      'E-poçt və ya şifrə səhvdir',
    );
  });

  test('FastAPI 422 siyahısını oxunaqlı mətnə çevirir', () => {
    // Real risk: `detail` siyahıdır, birbaşa göstərsək istifadəçi
    // "[object Object]" görər.
    const payload = {
      detail: [
        { loc: ['body', 'email'], msg: 'value is not a valid email address' },
        { loc: ['body', 'password'], msg: 'String should have at least 8 characters' },
      ],
    };
    const message = extractErrorMessage(422, payload);
    assert.match(message, /valid email address/);
    assert.match(message, /at least 8 characters/);
    assert.ok(!message.includes('[object Object]'));
  });

  test('boş siyahı üçün də mənalı mesaj qaytarır', () => {
    assert.equal(extractErrorMessage(422, { detail: [] }), 'Göndərilən məlumat düzgün deyil.');
  });

  test('detail olmayanda statusa görə mesaj seçir', () => {
    assert.match(extractErrorMessage(401, null), /yenidən daxil olun/);
    assert.match(extractErrorMessage(403, {}), /icazəniz yoxdur/);
    assert.match(extractErrorMessage(500, null), /Serverdə xəta/);
  });

  test('boş sətir olan detail-i qəbul etmir', () => {
    assert.match(extractErrorMessage(500, { detail: '   ' }), /Serverdə xəta/);
  });
});

describe('sessiya yaddaşı', () => {
  test('saxlayır və oxuyur', () => {
    saveSession({ token: 'abc123', user: { id: 7, display_name: 'Əli', is_teacher: true } });
    assert.equal(getToken(), 'abc123');
    assert.equal(getUser().display_name, 'Əli');
    assert.equal(getUser().is_teacher, true);
    assert.equal(isLoggedIn(), true);
  });

  test('təmizləyəndən sonra boş qalır', () => {
    saveSession({ token: 'abc', user: { id: 1 } });
    clearSession();
    assert.equal(getToken(), null);
    assert.equal(getUser(), null);
    assert.equal(isLoggedIn(), false);
  });

  test('korlanmış qeyd sessiyanı bloklamır', () => {
    saveSession({ token: 't', user: { id: 1 } });
    // Yaddaşdakı JSON-u əl ilə korla (məs. yarımçıq yazılma).
    const store = globalThis.localStorage;
    if (store) store.setItem('masterai.user', '{yarımçıq');
    // `getUser()` null qaytarmalıdır, ATMAMALIDIR.
    assert.doesNotThrow(() => getUser());
  });
});

describe('request', () => {
  const originalFetch = globalThis.fetch;

  function stubFetch(handler) {
    globalThis.fetch = handler;
  }

  test('uğurlu cavabı JSON kimi qaytarır', async () => {
    stubFetch(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    try {
      assert.deepEqual(await request('/health', { auth: false }), { ok: true });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test('token varsa Authorization başlığı göndərir', async () => {
    saveSession({ token: 'tok-42', user: { id: 1 } });
    let seen = null;
    stubFetch(async (_url, init) => {
      seen = init.headers;
      return new Response('{}', { status: 200 });
    });
    try {
      await request('/chats');
      assert.equal(seen.Authorization, 'Bearer tok-42');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test('auth:false olanda token göndərmir', async () => {
    saveSession({ token: 'tok-42', user: { id: 1 } });
    let seen = null;
    stubFetch(async (_url, init) => {
      seen = init.headers;
      return new Response('{}', { status: 200 });
    });
    try {
      await request('/auth/login', { method: 'POST', auth: false, body: {} });
      assert.equal(seen.Authorization, undefined);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test('HTTP xətasını ApiError-a çevirir və statusu saxlayır', async () => {
    stubFetch(
      async () => new Response(JSON.stringify({ detail: 'Tapılmadı' }), { status: 404 }),
    );
    try {
      await assert.rejects(
        () => request('/yoxdur'),
        (err) => err instanceof ApiError && err.status === 404 && err.message === 'Tapılmadı',
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test('şəbəkə xətasını status=0 ilə fərqləndirir', async () => {
    // CORS/oflayn hallarında `fetch` ATIR — HTTP statusu yoxdur.
    // Flutter tərəfində bu, geniş `catch (_)` içində itirdi.
    stubFetch(async () => {
      throw new TypeError('Failed to fetch');
    });
    try {
      await assert.rejects(
        () => request('/health', { auth: false }),
        (err) => err instanceof ApiError && err.status === 0 && /Serverə çıxmaq alınmadı/.test(err.message),
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test('204 cavabı üçün null qaytarır (gövdə yoxdur)', async () => {
    stubFetch(async () => new Response(null, { status: 204 }));
    try {
      assert.equal(await request('/nese', { method: 'DELETE' }), null);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test('gövdəsi JSON olmayan xəta cavabını da idarə edir', async () => {
    // nginx 502 qaytaranda gövdə HTML olur — `response.json()` atır.
    stubFetch(async () => new Response('<html>502</html>', { status: 502 }));
    try {
      await assert.rejects(
        () => request('/health', { auth: false }),
        (err) => err.status === 502 && /Serverdə xəta/.test(err.message),
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe('auth axını', () => {
  const originalFetch = globalThis.fetch;

  test('login uğurlu olanda sessiyanı saxlayır', async () => {
    globalThis.fetch = async (url, init) => {
      assert.match(url, /\/auth\/login$/);
      assert.equal(JSON.parse(init.body).email, 'ali@numune.az');
      return new Response(
        JSON.stringify({ token: 'yeni-token', user: { id: 3, display_name: 'Əli' } }),
        { status: 200 },
      );
    };
    try {
      await login('ali@numune.az', 'parol1234');
      assert.equal(getToken(), 'yeni-token');
      assert.equal(getUser().display_name, 'Əli');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test('register backend-in gözlədiyi `display_name` açarını göndərir', async () => {
    // Backend `RegisterRequest.display_name` gözləyir (server/models.py) —
    // camelCase göndərsək 422 alarıq.
    let body = null;
    globalThis.fetch = async (_url, init) => {
      body = JSON.parse(init.body);
      return new Response(JSON.stringify({ token: 't', user: { id: 1 } }), { status: 201 });
    };
    try {
      await register('yeni@numune.az', 'parol1234', 'Yeni İstifadəçi', { courseCode: 'K7M-3QX' });
      assert.deepEqual(Object.keys(body).sort(), ['course_code', 'display_name', 'email', 'password']);
      assert.equal(body.display_name, 'Yeni İstifadəçi');
      assert.equal(body.course_code, 'K7M-3QX');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test('register dəvət linki ilə YALNIZ invite_token göndərir', async () => {
    // Backend DƏQİQ BİRİNİ tələb edir (server/models.py RegisterRequest) -
    // ikisi birlikdə gəlsə 422.
    let body = null;
    globalThis.fetch = async (_url, init) => {
      body = JSON.parse(init.body);
      return new Response(JSON.stringify({ token: 't', user: { id: 1 } }), { status: 201 });
    };
    try {
      await register('m@numune.az', 'parol1234', 'Müəllim', { inviteToken: 'abc', courseCode: 'X' });
      assert.equal(body.invite_token, 'abc');
      assert.equal('course_code' in body, false);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test('login uğursuz olanda sessiya YARANMIR', async () => {
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ detail: 'E-poçt və ya şifrə səhvdir' }), { status: 401 });
    try {
      await assert.rejects(() => login('ali@numune.az', 'sehv'));
      assert.equal(getToken(), null);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
