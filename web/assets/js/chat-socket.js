/* Çat WebSocket-i - ümumi `ReconnectingSocket` bazası üzərində.
 *
 * Flutter tətbiqində avtomatik yenidən qoşulma YOX idi (bax
 * `app/README.md`): bağlantı kəsiləndə istifadəçi çatdan çıxıb yenidən
 * girməli idi.
 *
 * Brauzer WebSocket API-si başlıq göndərə bilmir. JWT URL-ə YAZILMIR:
 * hər qoşulmadan əvvəl `fetchWsTicket` birdəfəlik ticket alır.
 */

import { WS_BASE_URL } from './config.js';
import { normalizeHistory, normalizeLiveEvent } from './chat-item.js';
import { fetchWsTicket } from './api.js';
import { ReconnectingSocket, withTicket } from './socket.js';

export { computeBackoffDelay, isFatalCloseCode } from './socket.js';

export class ChatSocket {
  constructor(options) {
    this.options = options;
    this.socket = new ReconnectingSocket({
      url: withTicket(options.getTicket || fetchWsTicket, (ticket) => `${WS_BASE_URL}/ws/chat/${options.chatId}`
        + `?ticket=${encodeURIComponent(ticket)}`),
      socketFactory: options.socketFactory,
      onStatus: options.onStatus,
      onMessage: (data) => this._handle(data),
    });
  }

  _handle(data) {
    if (data.type === 'history') {
      this.options.onHistory(normalizeHistory(data.messages));
      return;
    }
    if (data.type === 'error') {
      if (this.options.onServerError) this.options.onServerError(data.detail || 'Xəta');
      return;
    }
    /* Canlı sessiya elanı mesaj AXININA girmir - o, çatın yuxarısında
       ayrıca kart kimi görünür (istifadəçinin tələbi: «QRUPDA MÜƏLLİM
       SESSİYA BAŞLADANDA HAMI GÖRƏ BİLƏCƏK»). `normalizeLiveEvent` onu
       tanımadığı üçün sükutla ataraq İTİRİRDİ. */
    if (data.type === 'live_session') {
      if (this.options.onLiveSession) this.options.onLiveSession(data);
      return;
    }
    const item = normalizeLiveEvent(data);
    if (item) this.options.onItem(item);
  }

  connect() {
    this.socket.connect();
  }

  sendText(content) {
    return this.socket.send({ type: 'text', content });
  }

  sendAnswer(questionId, chosenIndex) {
    return this.socket.send({
      type: 'answer', question_id: questionId, chosen_index: chosenIndex,
    });
  }

  close() {
    this.socket.close();
  }
}
