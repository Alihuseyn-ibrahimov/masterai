/* Canlı sessiya - host və oyunçu tərəfi.
 *
 * Sessiya modeli fərdi templidir (2026-09-08 dəyişikliyi): hər tələbə
 * öz "Növbəti sual" düyməsi ilə irəliləyir, müəllim isə ÜMUMİ vaxt
 * büdcəsi təyin edir. Ona görə oyunçu iki fərqli "bitdi" halı görür:
 *   `personal_finished` - özü bitirib (yalnız öz nəticəsi),
 *   `finished` - sessiya bitib (tam liderlik cədvəli).
 */

import { WS_BASE_URL } from './config.js';
import { ReconnectingSocket } from './socket.js';

/** Saniyəni `m:ss` şəklinə salır. Mənfi dəyər 0 sayılır - vaxt
 *  bitəndən sonra "-0:03" göstərmək mənasızdır. */
export function formatCountdown(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, '0')}`;
}

/** Müəllimin seçə biləcəyi vaxt büdcələri (dəqiqə). */
export const DURATION_CHOICES_MINUTES = [1, 2, 3, 5, 10];

/** İştirakçı tərəqqisini faizə çevirir. */
export function progressPercent(answered, total) {
  if (!total || total <= 0) return 0;
  return Math.min(100, Math.round((Math.max(0, answered) / total) * 100));
}

/**
 * Host ekranının iştirakçı sətirlərini qurur.
 *
 * `participants` serverdən (`state`/`participant_joined`), `progress`
 * isə `participant_progress` hadisələrindən yığılır - ikisi AYRI gəlir,
 * burada birləşdirilir.
 */
export function participantRows(participants, progressById, totalQuestions) {
  return (participants || []).map((participant) => {
    const answered = progressById.get(participant.id) || 0;
    return {
      id: participant.id,
      name: participant.display_name || `İştirakçı #${participant.id}`,
      answered,
      total: totalQuestions,
      percent: progressPercent(answered, totalQuestions),
      finished: totalQuestions > 0 && answered >= totalQuestions,
    };
  });
}

export class LiveHostSocket {
  /** Sessiya ID-si ilə. PIN yolu əvəzləndi: sessiya artıq bir sinfə
   *  (qrup çatına) bağlıdır və konsol YALNIZ onu başladan müəllimə
   *  açılır - server bunu `created_by` ilə yoxlayır. */
  constructor({ sessionId, token, onMessage, onStatus, socketFactory }) {
    this.socket = new ReconnectingSocket({
      url: () => `${WS_BASE_URL}/ws/live/sessions/${encodeURIComponent(sessionId)}/host`
        + `?token=${encodeURIComponent(token)}`,
      socketFactory,
      onStatus,
      onMessage,
    });
  }

  connect() { this.socket.connect(); }

  /** `duration_seconds` backend-in gözlədiyi açardır; müsbət tam ədəd
   *  olmasa server öz defoltunu işlədir. */
  start(durationSeconds) {
    return this.socket.send({ action: 'start', duration_seconds: durationSeconds });
  }

  close() { this.socket.close(); }
}

export class LivePlaySocket {
  /** Token MƏCBURİDİR və ad GÖNDƏRİLMİR - server adı hesabdan götürür,
   *  üzvlüyü isə çatdan yoxlayır. Yəni tələbə heç nə yazmır.
   *
   *  Köhnə PIN yolundan fərq: orada `display_name` ilk mesajda
   *  göndərilirdi və token KÖNÜLLÜ idi (anonim iştirakçı heç bir
   *  hesaba bağlanmırdı, ona görə fərdi tarixçə boş qalırdı). */
  constructor({ sessionId, token, onMessage, onStatus, socketFactory }) {
    this.socket = new ReconnectingSocket({
      url: () => `${WS_BASE_URL}/ws/live/sessions/${encodeURIComponent(sessionId)}/play`
        + `?token=${encodeURIComponent(token)}`,
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
