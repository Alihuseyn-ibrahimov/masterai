/* PIN ilə qonaq qoşulması (2026-10-30, istifadəçi qərarı ilə qayıdıb).
 *
 * AYRI MODULDUR, `live-socket.js`-ə əlavə edilmədi: o fayl artıq
 * brauzerlərdə keşdədir və köhnə nüsxədə bu ixraclar yoxdur - yeni
 * səhifə onu idxal etsə, köhnə keşlə modul yüklənməsi sınardı (bax
 * `live-socket.js`-in başlığındakı `live.js` hadisəsi).
 *
 * Hesabsız tələbə adını yazır; brauzerdə yaranan `guestKey` isə
 * səhifə yenilənəndə serverə «bu mənəm» deyir, yoxsa hər yeniləmə
 * yeni iştirakçı sətri yaradardı (sessiya #31 bug-ı).
 */

import { WS_BASE_URL } from './config.js';
import { fetchWsTicket } from './api.js';
import { ReconnectingSocket } from './socket.js';

export const PIN_LENGTH = 6;
export const GUEST_NAME_MAX = 40;

/** İstifadəçinin yazdığı PIN-dən rəqəmləri saxlayır («123 456» da keçir). */
export function normalizePin(raw) {
  return String(raw || '').replace(/\D/g, '');
}

export function isValidPin(pin) {
  return new RegExp(`^\\d{${PIN_LENGTH}}$`).test(pin);
}

/** Tələbəyə paylaşılan link: açılanda PIN özü doldurulur. */
export function joinLink(pin, origin) {
  return `${origin}/qosul.html?pin=${encodeURIComponent(pin)}`;
}

function randomKey(cryptoImpl) {
  const bytes = new Uint8Array(12);
  cryptoImpl.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Bu PIN üçün brauzer açarı - yoxdursa yaradılıb saxlanılır.
 *  Yaddaş bloklanıbsa (Safari gizli rejimi) hər dəfə yeni açar olur:
 *  qoşulma işləyir, sadəcə yeniləmədə yeni sətir yaranar. */
export function guestKey(pin, { storage = globalThis.localStorage, cryptoImpl = globalThis.crypto } = {}) {
  const name = `masterai-guest-${pin}`;
  try {
    const saved = storage.getItem(name);
    if (saved) return saved;
  } catch { /* yaddaş bloklanıb */ }
  const key = randomKey(cryptoImpl);
  try { storage.setItem(name, key); } catch { /* yaddaş bloklanıb */ }
  return key;
}

export class LivePinPlaySocket {
  /** Token KÖNÜLLÜDÜR: sinif üzvü daxil olubsa, server onu hesabı ilə
   *  qoşur (nəticə tarixçəsinə düşür); əks halda ad + açar ilə qonaq. */
  constructor({ pin, name, guest, token, onMessage, onStatus, socketFactory, getTicket = fetchWsTicket }) {
    const base = () => `${WS_BASE_URL}/ws/live/pin/${encodeURIComponent(pin)}/play`
      + `?name=${encodeURIComponent(name)}&guest=${encodeURIComponent(guest)}`;
    this.socket = new ReconnectingSocket({
      /* Daxil olmuş tələbə JWT-ni URL-ə yazmır, birdəfəlik ticket alır.
         Ticket alınmasa (sessiya bitib, şəbəkə) qonaq kimi qoşulur -
         PIN səhifəsi hesabsız da işləməlidir. */
      url: () => {
        if (!token) return base();
        let ticket;
        try {
          ticket = getTicket();
        } catch {
          return base();
        }
        const build = (value) => (value ? `${base()}&ticket=${encodeURIComponent(value)}` : base());
        if (ticket && typeof ticket.then === 'function') return ticket.then(build, () => base());
        return build(ticket);
      },
      socketFactory,
      onStatus,
      onMessage,
    });
  }

  connect() { this.socket.connect(); }

  answer(questionIndex, chosenIndex) {
    return this.socket.send({
      type: 'answer', question_index: questionIndex, chosen_index: chosenIndex,
    });
  }

  next() { return this.socket.send({ type: 'next' }); }

  close() { this.socket.close(); }
}
