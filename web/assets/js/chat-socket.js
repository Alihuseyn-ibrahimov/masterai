/* Çat WebSocket-i - ümumi `ReconnectingSocket` bazası üzərində.
 *
 * Flutter tətbiqində avtomatik yenidən qoşulma YOX idi (bax
 * `app/README.md`): bağlantı kəsiləndə istifadəçi çatdan çıxıb yenidən
 * girməli idi.
 *
 * Token sorğu parametrindədir (`?token=...`) - brauzer WebSocket API-si
 * xüsusi başlıq göndərməyə imkan vermir. Bu, backend-in mövcud
 * müqaviləsidir; bilinən risk kimi `masterai/CLAUDE.md`-də qeyd olunub.
 */

import { WS_BASE_URL } from './config.js';
import { normalizeHistory, normalizeLiveEvent } from './chat-item.js';
import { ReconnectingSocket } from './socket.js';

export { computeBackoffDelay, isFatalCloseCode } from './socket.js';

export class ChatSocket {
  constructor(options) {
    this.options = options;
    this.socket = new ReconnectingSocket({
      url: () => `${WS_BASE_URL}/ws/chat/${options.chatId}`
        + `?token=${encodeURIComponent(options.token)}`,
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
