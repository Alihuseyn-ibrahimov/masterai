/* Dərs səsinin yazılması (Classroom, gün 3).
 *
 * Müəllimin mikrofonu ~5 dəqiqəlik MÜSTƏQİL hissələrlə yazılır: hər
 * hissə üçün yeni MediaRecorder açılır, yəni hər fayl öz başlığı olan
 * tam səs faylıdır və Whisper onu ayrıca oxuya bilir. Bir hissə itsə
 * (şəbəkə), qalan dərs itmir.
 *
 * Saf köməkçilər (`pickMimeType`, `extensionFor`) Node-da test olunur;
 * `createLessonRecorder` brauzer API-ləri inyeksiya ilə alır.
 */

export const SEGMENT_MS = 5 * 60 * 1000;

const PREFERRED = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];

/** Brauzerin dəstəklədiyi ilk format; heç biri yoxdursa ''. Safari
 *  webm yazmır, mp4 yazır - ona görə siyahı bir neçə formatdır. */
export function pickMimeType(isTypeSupported) {
  if (typeof isTypeSupported !== 'function') return '';
  return PREFERRED.find((type) => {
    try {
      return isTypeSupported(type);
    } catch {
      return false;
    }
  }) || '';
}

/** Server faylı uzantısına görə qəbul edir. */
export function extensionFor(mimeType) {
  const type = String(mimeType || '').split(';')[0].trim();
  if (type === 'audio/ogg') return '.ogg';
  if (type === 'audio/mp4') return '.m4a';
  return '.webm';
}

/**
 * @param {object} deps
 * @param {MediaStream} deps.stream          yazılacaq səs
 * @param {Function} deps.Recorder           MediaRecorder konstruktoru
 * @param {(blob: Blob, seq: number, ext: string) => Promise} deps.upload
 * @param {(state: object) => void} [deps.onChange]
 * @param {number} [deps.segmentMs]
 * @param {number} [deps.firstSeq]           yenidən girəndə davam nömrəsi
 */
export function createLessonRecorder({
  stream, Recorder, upload, onChange = () => {}, segmentMs = SEGMENT_MS, firstSeq = 0,
  setTimer = setTimeout, clearTimer = clearTimeout,
}) {
  const mimeType = pickMimeType(Recorder && Recorder.isTypeSupported);
  const ext = extensionFor(mimeType);
  let seq = firstSeq;
  let current = null;
  let timer = null;
  let running = false;
  const pending = new Set();
  const state = { recording: false, sent: 0, failed: 0 };
  const emit = () => onChange({ ...state, recording: running });

  function send(blob, number) {
    if (!blob.size) return;
    // Bir dəfə təkrar: mobil şəbəkənin anlıq kəsilməsi hissəni itirməsin.
    const job = upload(blob, number, ext)
      .catch(() => upload(blob, number, ext))
      .then(() => { state.sent += 1; }, () => { state.failed += 1; })
      .finally(() => { pending.delete(job); emit(); });
    pending.add(job);
  }

  function startSegment() {
    const chunks = [];
    const number = seq;
    seq += 1;
    const recorder = new Recorder(stream, mimeType ? { mimeType } : undefined);
    recorder.addEventListener('dataavailable', (event) => {
      if (event.data && event.data.size) chunks.push(event.data);
    });
    recorder.addEventListener('stop', () => {
      send(new Blob(chunks, { type: mimeType || 'audio/webm' }), number);
    });
    recorder.start();
    current = recorder;
    timer = setTimer(() => {
      // Növbəti hissə köhnəsi dayanmadan açılır: arada boşluq qalmasın.
      const finished = current;
      if (running) startSegment();
      finished.stop();
    }, segmentMs);
  }

  return {
    get nextSeq() { return seq; },
    start() {
      if (running) return;
      running = true;
      startSegment();
      emit();
    },
    /** Yazını dayandırır və bütün hissələrin göndərilməsini gözləyir. */
    async stop() {
      if (!running) return;
      running = false;
      clearTimer(timer);
      if (current && current.state !== 'inactive') {
        const done = new Promise((resolve) => current.addEventListener('stop', resolve, { once: true }));
        current.stop();
        await done;
      }
      current = null;
      emit();
      await Promise.allSettled([...pending]);
    },
  };
}
