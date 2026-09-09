/* Çat WebSocket-i — avtomatik yenidən qoşulma ilə.
 *
 * Flutter tətbiqində bu YOX idi (bax `app/README.md`, "Bilinən
 * məhdudiyyətlər"): bağlantı kəsiləndə istifadəçi çatdan çıxıb yenidən
 * girməli idi. Burada bağlantı özü bərpa olunur.
 *
 * Token sorğu parametrindədir (`?token=...`) — brauzer WebSocket API-si
 * xüsusi başlıq göndərməyə imkan vermir. Bu, backend-in mövcud
 * müqaviləsidir; bilinən risk kimi `masterai/CLAUDE.md`-də qeyd olunub.
 */

import { WS_BASE_URL } from './config.js';
import { normalizeHistory, normalizeLiveEvent } from './chat-item.js';

/** Serverin "səni buraxmıram" cavabları — yenidən qoşulmaq MƏNASIZDIR
 *  və serveri boş yerə yükləyər (bax `chat_websocket`, app.py). */
const FATAL_CLOSE_CODES = new Set([
  4401, // token etibarsızdır
  4403, // bu çatın üzvü deyilsən
  4404, // çat tapılmadı
]);

export function isFatalCloseCode(code) {
  return FATAL_CLOSE_CODES.has(code);
}

const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 30000;

/** Eksponensial gözləmə — server ayağa qalxana qədər sorğu yağdırmamaq
 *  üçün. Təsadüfi əlavə ("jitter") eyni anda kəsilən çoxlu client-in
 *  serverə eyni saniyədə qayıtmasının qarşısını alır. */
export function computeBackoffDelay(attempt, random = Math.random) {
  const exponential = Math.min(BASE_DELAY_MS * 2 ** Math.max(0, attempt), MAX_DELAY_MS);
  const jitter = exponential * 0.2 * random();
  // Hədd SON nəticəyə tətbiq olunur: jitter özü ±10% olduğu üçün, onu
  // yalnız eksponensial hissəyə tətbiq etsək yekun dəyər həddi 10%
  // aşardı (real testdə tapıldı — 30s hədd 33s verirdi).
  const withJitter = exponential - exponential * 0.1 + jitter;
  return Math.round(Math.min(withJitter, MAX_DELAY_MS));
}

export class ChatSocket {
  /**
   * @param {object} options
   * @param {number} options.chatId
   * @param {string} options.token
   * @param {(items: object[]) => void} options.onHistory
   * @param {(item: object) => void} options.onItem
   * @param {(detail: string) => void} [options.onServerError]
   * @param {(status: 'connecting'|'open'|'reconnecting'|'closed') => void} [options.onStatus]
   * @param {typeof WebSocket} [options.socketFactory] — testlər üçün
   */
  constructor(options) {
    this.options = options;
    this.socket = null;
    this.attempt = 0;
    this.stopped = false;
    this.timer = null;
  }

  _emitStatus(status) {
    if (this.options.onStatus) this.options.onStatus(status);
  }

  connect() {
    if (this.stopped) return;
    const Factory = this.options.socketFactory || globalThis.WebSocket;
    const url = `${WS_BASE_URL}/ws/chat/${this.options.chatId}`
      + `?token=${encodeURIComponent(this.options.token)}`;

    this._emitStatus(this.attempt === 0 ? 'connecting' : 'reconnecting');
    this.socket = new Factory(url);

    this.socket.onopen = () => {
      this.attempt = 0;
      this._emitStatus('open');
    };

    this.socket.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return; // oxunmayan çərçivə bağlantını qırmamalıdır
      }
      if (data.type === 'history') {
        this.options.onHistory(normalizeHistory(data.messages));
        return;
      }
      if (data.type === 'error') {
        if (this.options.onServerError) this.options.onServerError(data.detail || 'Xəta');
        return;
      }
      const item = normalizeLiveEvent(data);
      if (item) this.options.onItem(item);
    };

    this.socket.onclose = (event) => {
      if (this.stopped) return;
      if (isFatalCloseCode(event && event.code)) {
        this._emitStatus('closed');
        return;
      }
      this._scheduleReconnect();
    };

    // `onerror`-dan sonra brauzer HƏMİŞƏ `onclose` çağırır — yenidən
    // qoşulma yalnız orada planlaşdırılır ki, iki dəfə olmasın.
    this.socket.onerror = () => {};
  }

  _scheduleReconnect() {
    const delay = computeBackoffDelay(this.attempt);
    this.attempt += 1;
    this._emitStatus('reconnecting');
    this.timer = setTimeout(() => this.connect(), delay);
  }

  sendText(content) {
    if (!this.socket || this.socket.readyState !== 1) return false;
    this.socket.send(JSON.stringify({ type: 'text', content }));
    return true;
  }

  sendAnswer(questionId, chosenIndex) {
    if (!this.socket || this.socket.readyState !== 1) return false;
    this.socket.send(JSON.stringify({
      type: 'answer', question_id: questionId, chosen_index: chosenIndex,
    }));
    return true;
  }

  close() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    if (this.socket) this.socket.close();
    this._emitStatus('closed');
  }
}
