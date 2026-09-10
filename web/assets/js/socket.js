/* Yenidən qoşulan WebSocket bazası.
 *
 * Üç yerdə eyni davranış lazımdır (çat, canlı sessiya hostu, canlı
 * sessiya oyunçusu) - məntiq bir dəfə burada yazılır.
 */

/** Serverin "səni buraxmıram" cavabları - yenidən qoşulmaq MƏNASIZDIR
 *  və serveri boş yerə yükləyər. Backend bu kodları işlədir:
 *  4400 yararsız qoşulma mesajı, 4401 token, 4403 üzv deyil,
 *  4404 tapılmadı, 4409 sessiya qoşulmağa açıq deyil. */
const FATAL_CLOSE_CODES = new Set([4400, 4401, 4403, 4404, 4409]);

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
   * @param {() => string} options.url - hər cəhddə yenidən hesablanır
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
    const Factory = this.options.socketFactory || globalThis.WebSocket;
    this._status(this.attempt === 0 ? 'connecting' : 'reconnecting');
    this.socket = new Factory(this.options.url());

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
        return;
      }
      const delay = computeBackoffDelay(this.attempt);
      this.attempt += 1;
      this._status('reconnecting');
      this.timer = setTimeout(() => this.connect(), delay);
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
