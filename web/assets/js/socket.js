/* Yenidən qoşulan WebSocket bazası.
 *
 * Üç yerdə eyni davranış lazımdır (çat, canlı sessiya hostu, canlı
 * sessiya oyunçusu) - məntiq bir dəfə burada yazılır.
 */

import { goToClosedPage, LICENSE_CLOSED_WS_CODE } from './license.js';

/** Serverin "səni buraxmıram" cavabları - yenidən qoşulmaq MƏNASIZDIR
 *  və serveri boş yerə yükləyər. Backend bu kodları işlədir:
 *  4400 yararsız qoşulma mesajı, 4401 token, 4402 kursun abunəsi bitib,
 *  4403 üzv deyil, 4404 tapılmadı, 4409 sessiya doludur və ya açıq deyil,
 *  4429 çox sayda səhv PIN. */
const FATAL_CLOSE_CODES = new Set([4400, 4401, LICENSE_CLOSED_WS_CODE, 4403, 4404, 4409, 4429]);

export function isFatalCloseCode(code) {
  return FATAL_CLOSE_CODES.has(code);
}

const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 30000;

/** Eksponensial gözləmə + təsadüfi əlavə ("jitter"): eyni anda kəsilən
 *  çoxlu client serverə eyni saniyədə qayıtmamalıdır. */
export function computeBackoffDelay(attempt, random = Math.random) {
  const exponential = Math.min(BASE_DELAY_MS * 2 ** Math.max(0, attempt), MAX_DELAY_MS);
  const jitter = exponential * 0.2 * random();
  // Hədd SON nəticəyə tətbiq olunur: jitter ±10% olduğu üçün, yalnız
  // eksponensial hissəyə tətbiq etsək yekun dəyər həddi aşardı (real
  // testdə tapıldı - 30s hədd 33s verirdi).
  return Math.round(Math.min(exponential - exponential * 0.1 + jitter, MAX_DELAY_MS));
}

export class ReconnectingSocket {
  /**
   * @param {object} options
   * @param {() => string|Promise<string>} options.url - hər cəhddə yenidən
   *        hesablanır; Promise olsa (ticket sorğusu) gözlənilir
   * @param {(data: object) => void} options.onMessage
   * @param {(status: 'connecting'|'open'|'reconnecting'|'closed') => void} [options.onStatus]
   * @param {(socket: WebSocket) => void} [options.onOpen] - qoşulan kimi
   *        göndəriləsi ilk mesaj üçün (məs. oyunçunun `display_name`-i)
   * @param {typeof WebSocket} [options.socketFactory]
   */
  constructor(options) {
    this.options = options;
    this.socket = null;
    this.attempt = 0;
    this.stopped = false;
    this.timer = null;
  }

  _status(status) {
    if (this.options.onStatus) this.options.onStatus(status);
  }

  connect() {
    if (this.stopped) return;
    this._status(this.attempt === 0 ? 'connecting' : 'reconnecting');
    let url;
    try {
      url = this.options.url();
    } catch (error) {
      this._urlFailed(error);
      return;
    }
    // Ünvan Promise ola bilər: hər cəhddə serverdən YENİ birdəfəlik
    // ticket alınır (bax `server/ws_ticket.py`).
    if (url && typeof url.then === 'function') {
      url.then((resolved) => this._open(resolved), (error) => this._urlFailed(error));
    } else {
      this._open(url);
    }
  }

  /** Ticket alınmadı. 401: sessiya bitib - yenidən cəhd mənasızdır.
   *  402: kursun abunəsi bitib. Qalan hallar (şəbəkə, 5xx) - gözləyib
   *  yenidən cəhd. */
  _urlFailed(error) {
    if (this.stopped) return;
    const status = error && error.status;
    if (status === 401 || status === 403 || status === 402) {
      this._status('closed');
      return;
    }
    this._scheduleReconnect();
  }

  _scheduleReconnect() {
    const delay = computeBackoffDelay(this.attempt);
    this.attempt += 1;
    this._status('reconnecting');
    this.timer = setTimeout(() => this.connect(), delay);
  }

  _open(url) {
    if (this.stopped) return;
    const Factory = this.options.socketFactory || globalThis.WebSocket;
    this.socket = new Factory(url);

    this.socket.onopen = () => {
      this.attempt = 0;
      this._status('open');
      if (this.options.onOpen) this.options.onOpen(this.socket);
    };

    this.socket.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return; // oxunmayan çərçivə bağlantını qırmamalıdır
      }
      this.options.onMessage(data);
    };

    this.socket.onclose = (event) => {
      if (this.stopped) return;
      if (isFatalCloseCode(event && event.code)) {
        this._status('closed');
        if (event.code === LICENSE_CLOSED_WS_CODE) goToClosedPage();
        return;
      }
      this._scheduleReconnect();
    };

    // `onerror`-dan sonra brauzer HƏMİŞƏ `onclose` çağırır - yenidən
    // qoşulma yalnız orada planlaşdırılır ki, iki dəfə olmasın.
    this.socket.onerror = () => {};
  }

  /** Göndərir; bağlantı açıq deyilsə `false` qaytarır (istifadəçi
   *  mesajın getdiyini sanmamalıdır). */
  send(payload) {
    if (!this.socket || this.socket.readyState !== 1) return false;
    this.socket.send(JSON.stringify(payload));
    return true;
  }

  close() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    if (this.socket) this.socket.close();
    this._status('closed');
  }
}

/** Ünvanı birdəfəlik ticket ilə qurur. `getTicket` sinxron dəyər də
 *  qaytara bilər (testlər) - onda bağlantı dərhal açılır. */
export function withTicket(getTicket, build) {
  return () => {
    const ticket = getTicket();
    if (ticket && typeof ticket.then === 'function') return ticket.then(build);
    return build(ticket);
  };
}
