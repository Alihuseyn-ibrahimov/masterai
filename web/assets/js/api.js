/* MasterAI - backend client-i.
 *
 * Mövcud JWT API-sinə qarşı işləyir; backend DƏYİŞMƏYİB (540+ test).
 * Modul həm brauzerdə (`<script type="module">`), həm də Node-da
 * (`node --test`) işləyir - ona görə brauzerə xas heç nə modul
 * səviyyəsində çağırılmır.
 */

import { API_BASE_URL } from './config.js';
import { goToClosedPage, LICENSE_CLOSED_STATUS } from './license.js';

const TOKEN_KEY = 'masterai.token';
const USER_KEY = 'masterai.user';

/** Xəta obyektinin özü - `status` ilə çağıran tərəf qərar verə bilir
 *  (məs. 401 → giriş səhifəsinə yönləndir). */
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/* `localStorage` HƏR MÜHİTDƏ MÖVCUD DEYİL və mövcud olanda belə ATA
 * BİLƏR: Safari-nin gizli rejimi, kuki bloklanan brauzerlər, `file://`
 * sxemi bəzi konfiqurasiyalarda. Belə halda tətbiq TAM SINMAMALIDIR - * yaddaş yalnız bu sekmə üçün müvəqqəti olur. */
const memoryStore = new Map();

function safeStorage() {
  try {
    const ls = globalThis.localStorage;
    if (!ls) return null;
    // Yazma icazəsini həqiqətən yoxla - bəzi brauzerlərdə obyekt var,
    // amma `setItem` atır.
    const probe = '__masterai_probe__';
    ls.setItem(probe, '1');
    ls.removeItem(probe);
    return ls;
  } catch {
    return null;
  }
}

function readValue(key) {
  const store = safeStorage();
  if (store) {
    try {
      return store.getItem(key);
    } catch {
      /* aşağıdakı yaddaş ehtiyatına düş */
    }
  }
  return memoryStore.has(key) ? memoryStore.get(key) : null;
}

function writeValue(key, value) {
  const store = safeStorage();
  if (store) {
    try {
      store.setItem(key, value);
      return;
    } catch {
      /* aşağıdakı yaddaş ehtiyatına düş */
    }
  }
  memoryStore.set(key, value);
}

function removeValue(key) {
  const store = safeStorage();
  if (store) {
    try {
      store.removeItem(key);
    } catch {
      /* yalnız yaddaş ehtiyatı qalır */
    }
  }
  memoryStore.delete(key);
}

/* ---- Sessiya ---- */

export function getToken() {
  return readValue(TOKEN_KEY);
}

export function getUser() {
  const raw = readValue(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    // Korlanmış qeyd sessiyanı tamamilə bloklamamalıdır.
    return null;
  }
}

export function isLoggedIn() {
  return Boolean(getToken());
}

export function saveSession(auth) {
  writeValue(TOKEN_KEY, auth.token);
  writeValue(USER_KEY, JSON.stringify(auth.user));
}

export function clearSession() {
  removeValue(TOKEN_KEY);
  removeValue(USER_KEY);
}

/* ---- Xəta mesajı ---- */

/** Backend xətanı `{"detail": "..."}` kimi Azərbaycan dilində qaytarır
 *  və biz onu olduğu kimi göstəririk. AMMA FastAPI-nin doğrulama
 *  xətası (422) `detail`-i OBYEKT SİYAHISI kimi qaytarır - onu birbaşa
 *  göstərmək istifadəçiyə "[object Object]" çıxarır. */
export function extractErrorMessage(status, payload) {
  const detail = payload && payload.detail;

  if (typeof detail === 'string' && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item.msg === 'string' ? item.msg : null))
      .filter(Boolean);
    if (messages.length) return messages.join('; ');
    return 'Göndərilən məlumat düzgün deyil.';
  }

  if (status === 401) return 'Sessiyanın vaxtı bitib, yenidən daxil olun.';
  if (status === 403) return 'Bu əməliyyat üçün icazəniz yoxdur.';
  if (status === 404) return 'Tapılmadı.';
  if (status >= 500) return 'Serverdə xəta baş verdi, bir azdan yenidən cəhd edin.';
  return 'Xəta baş verdi.';
}

/* ---- Sorğu ---- */

export async function request(path, options = {}) {
  const { method = 'GET', body, auth = true, signal } = options;

  const headers = {};
  // FormData (fayl yükləmə): Content-Type-ı brauzer özü `boundary` ilə qoyur.
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined || isForm ? body : JSON.stringify(body),
      signal,
    });
  } catch (cause) {
    // Şəbəkə xətası HTTP xətası DEYİL - `status` yoxdur. Flutter
    // tərəfində geniş `catch (_)` bunu digər xətalarla qarışdırırdı və
    // əsl səbəb (məs. CORS) gizlənirdi (bax masterai/CLAUDE.md,
    // "Dərs: veb host konsolunda CORS unudulmuşdu").
    // Xəta mətni istifadəçini GÜNAHLANDIRMIR: bu nöqtədə səbəbin
    // istifadəçinin internetində, yoxsa bizim serverimizdə olduğunu
    // bilmirik. «İnternetinizi yoxlayın» yanlış ünvan göstərə bilər.
    throw new ApiError('Serverə çıxmaq alınmadı. Bir azdan yenidən cəhd edin.', 0);
  }

  if (response.status === 204) return null;

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    // Kursun abunəsi bitib: HƏR səhifədə eyni davranış olsun deyə
    // yönləndirmə burada, tək yerdədir. Sessiya SİLİNMİR - ödənişdən
    // sonra tələbə yenidən giriş etmədən davam edir.
    if (response.status === LICENSE_CLOSED_STATUS) goToClosedPage();
    throw new ApiError(extractErrorMessage(response.status, payload), response.status);
  }
  return payload;
}

/* ---- Auth ---- */

/** WebSocket üçün birdəfəlik, 60 saniyəlik giriş. JWT URL-ə YAZILMIR:
 *  URL proksi jurnalında, tarixçədə qala bilər, ticket isə bir dəfə
 *  işləndikdən sonra yararsızdır. Hər yenidən qoşulmada yenisi alınır. */
export async function fetchWsTicket() {
  const reply = await request('/auth/ws-ticket', { method: 'POST' });
  return reply.ticket;
}

export async function login(email, password) {
  const auth = await request('/auth/login', {
    method: 'POST',
    auth: false,
    body: { email, password },
  });
  saveSession(auth);
  return auth;
}

/** Qapalı qeydiyyat: tələbə kurs kodu, müəllim dəvət tokeni ilə.
 *  Backend DƏQİQ BİRİNİ qəbul edir - dəvət varsa kod göndərilmir. */
export async function register(email, password, displayName, { courseCode, inviteToken } = {}) {
  const body = { email, password, display_name: displayName };
  if (inviteToken) body.invite_token = inviteToken;
  else body.course_code = courseCode || '';
  const auth = await request('/auth/register', {
    method: 'POST',
    auth: false,
    body,
  });
  saveSession(auth);
  return auth;
}
