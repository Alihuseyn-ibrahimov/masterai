/* Şəxsi dərs qeydinin avtomatik saxlanması (MasterAI Classroom, gün 5).
 *
 * Tələbə yazmağı dayandırandan `delayMs` sonra saxlanır, hər hərfdə yox.
 * Saxlama gedərkən yeni mətn gəlsə, bitəndən sonra SON mətn yenidən
 * göndərilir: iki sorğu yarışıb köhnə mətnin sonra yazılması mümkün
 * deyil. DOM tələb etmir, Node-da test olunur.
 *
 * Vəziyyətlər (`onState`): 'dirty' (yazılır), 'saving', 'saved', 'error'.
 */

export const NOTE_DELAY_MS = 1200;

export function createAutosave({
  save,
  onState = () => {},
  delayMs = NOTE_DELAY_MS,
  initial = '',
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  let saved = initial;
  let pending = null;   // hələ göndərilməmiş mətn
  let timer = null;
  let inFlight = null;  // gedən saxlamanın vədi

  async function run() {
    timer = null;
    if (inFlight || pending === null) return inFlight;
    const text = pending;
    pending = null;
    if (text === saved) {
      onState('saved');
      return null;
    }
    onState('saving');
    let ok = false;
    inFlight = (async () => {
      try {
        await save(text);
        saved = text;
        ok = true;
        onState(pending === null ? 'saved' : 'dirty');
      } catch (error) {
        // Göndərilməyən mətn itmir: növbəti yazıda və ya flush-da yenidən.
        // Özü-özünə təkrar YOX: internet yoxdursa hər saniyə sorğu olardı.
        if (pending === null) pending = text;
        onState('error', error);
      }
    })();
    await inFlight;
    inFlight = null;
    if (ok && pending !== null) schedule(pending);
    return null;
  }

  function schedule(text) {
    pending = text;
    onState('dirty');
    if (timer !== null) clearTimer(timer);
    timer = setTimer(run, delayMs);
  }

  /** Səhifədən çıxarkən: gözləmədən saxla. */
  async function flush() {
    if (timer !== null) {
      clearTimer(timer);
      timer = null;
    }
    if (inFlight) await inFlight;
    if (pending !== null) await run();
  }

  return { schedule, flush, get saved() { return saved; } };
}
