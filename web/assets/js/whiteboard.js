/* İnteraktiv lövhə (Faza 4, 2026-11-06): müəllimin dərs otağında çəkdiyi
 * xətlər LiveKit data kanalı ilə tələbələrə gedir.
 *
 * Koordinatlar [0,1] aralığına normallaşdırılır (ekran ölçüsündən asılı
 * olmasın - müəllimin monitoru tələbənin telefonundan fərqli ölçüdədir).
 * Çəkiliş `LOGICAL_SIZE x LOGICAL_SIZE`-lıq sabit daxili kətan üzərində
 * saxlanır: eyni kətan həm göstərilir (CSS ilə uyğunlaşdırılır), həm də
 * dərs bitəndə şəklə çevrilib mövcud `/live/lessons/{id}/board` OCR
 * axınına göndərilir - yeni backend kodu lazım deyil.
 */

export const LOGICAL_WIDTH = 1600;
export const LOGICAL_HEIGHT = 900;

/** Bir xətt parçası (pointer-in iki ardıcıl nöqtəsi). */
export function makeSegment(x0, y0, x1, y1, color) {
  return { t: 'seg', x0, y0, x1, y1, c: color };
}

export function makeClear() {
  return { t: 'clear' };
}

/** Piksel koordinatını [0,1]-ə çevirir (rect - kətanın `getBoundingClientRect()`-i). */
export function normalize(clientX, clientY, rect) {
  const w = rect.width || 1;
  const h = rect.height || 1;
  return {
    x: Math.min(1, Math.max(0, (clientX - rect.left) / w)),
    y: Math.min(1, Math.max(0, (clientY - rect.top) / h)),
  };
}

/** LiveKit `publishData` üçün: obyekt → bayt. */
export function encodeMessage(msg) {
  return new TextEncoder().encode(JSON.stringify(msg));
}

/** `DataReceived` üçün: bayt → obyekt (pozuq/naməlum mesaj → null). */
export function decodeMessage(bytes) {
  try {
    const msg = JSON.parse(new TextDecoder().decode(bytes));
    if (msg && (msg.t === 'seg' || msg.t === 'clear')) return msg;
    return null;
  } catch {
    return null;
  }
}

/** Bütün çəkilmiş xəttləri saxlayır - panel bağlıykən gələn mesajlar da
 *  itmir, sonra açılanda `replay` ilə yenidən çəkilir. */
export function createBoardState() {
  return { segments: [] };
}

export function applyMessage(state, msg) {
  if (msg.t === 'clear') state.segments = [];
  else if (msg.t === 'seg') state.segments.push(msg);
}

/** Bir seqmenti `ctx`-ə (2D canvas context) çəkir - sabit `LOGICAL_*`
 *  ölçüsünə görə. `ctx` test üçün sadə spy-obyekt ola bilər. */
export function drawSegment(ctx, seg) {
  ctx.strokeStyle = seg.c || '#1a1a1a';
  ctx.lineWidth = 4;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(seg.x0 * LOGICAL_WIDTH, seg.y0 * LOGICAL_HEIGHT);
  ctx.lineTo(seg.x1 * LOGICAL_WIDTH, seg.y1 * LOGICAL_HEIGHT);
  ctx.stroke();
}

/** Kətanı təmizləyib bütün saxlanmış seqmentləri yenidən çəkir. */
export function replay(ctx, state) {
  ctx.clearRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT);
  for (const seg of state.segments) drawSegment(ctx, seg);
}
