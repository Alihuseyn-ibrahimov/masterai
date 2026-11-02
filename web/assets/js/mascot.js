/* MasterAI maskotu: eynəkli bayquş (2026-11-02, «Dəftər + maskot» Faza 2).
 *
 * NİYƏ: sayt «əsl tədris tətbiqi» hissi versin deyə məhsulun öz personajı
 * olmalıdır. Bayquş boş siyahıda, AI hazırlayanda və quiz cavabında
 * reaksiya verir; masaüstündə gözləri kursoru izləyir. İlham: MotionSites
 * «Playful Idea» (orada video kadrları çəkilir, burada SVG - fayl kiçik,
 * kitabxana yoxdur).
 *
 * İstifadə:
 *   <span class="mascot" data-mascot="idle"></span>
 *   mountMascots(document, window)        // hamısını çəkir, gözləri izlədir
 *   setMascotState(el, 'happy')           // reaksiya
 *
 * Rənglər CSS-dədir (`.mascot__*`, tokenlərlə); burada yalnız forma.
 * Maskot bəzəkdir: `aria-hidden`. Mənası olan yerdə yanında mətn olmalıdır.
 */

/** Vəziyyətlər: gözləyir, sevinir (düzgün), təəccüblənir (səhv),
 *  düşünür (AI hazırlayır), yatır (boş siyahı). */
export const MASCOT_STATES = ['idle', 'happy', 'surprised', 'thinking', 'sleep'];

/** Göz yuvalarının mərkəzi və bəbəyin gedə biləcəyi radius (viewBox vahidi). */
export const EYES = [{ x: 42, y: 56 }, { x: 78, y: 56 }];
export const PUPIL_RANGE = 5;
/** Kursor bu qədər piksel uzaqda olanda bəbək tam kənara çatır. */
const FULL_LOOK_DISTANCE = 240;

/** Vəziyyətə görə sabit baxış (izləmə yalnız `idle`-da işləyir). */
const FIXED_LOOK = {
  thinking: { x: 3, y: -4 },
  surprised: { x: 0, y: 0 },
};

export function normalizeState(state) {
  return MASCOT_STATES.includes(state) ? state : 'idle';
}

/**
 * Bəbəyin sürüşməsi: göz mərkəzindən kursora istiqamət, uzunluğu
 * məsafə ilə artır və `range`-də kəsilir (yaxın kursor - kiçik hərəkət,
 * əks halda göz ən kiçik hərəkətdə «tullanar»).
 */
export function pupilOffset(dx, dy, range = PUPIL_RANGE, full = FULL_LOOK_DISTANCE) {
  const distance = Math.hypot(dx, dy);
  if (distance < 1) return { x: 0, y: 0 };
  const length = range * Math.min(1, distance / full);
  return { x: (dx / distance) * length, y: (dy / distance) * length };
}

const SVG = `
<svg viewBox="0 0 120 130" aria-hidden="true" focusable="false">
  <g class="mascot__figure">
    <path class="mascot__body" d="M28 32 L20 8 L44 22 Q60 16 76 22 L100 8 L92 32 C102 44 106 58 106 76 C106 106 86 126 60 126 C34 126 14 106 14 76 C14 58 18 44 28 32 Z"/>
    <path class="mascot__wing mascot__wing--left" d="M20 70 C6 84 10 104 26 110 C22 96 24 84 32 74 Z"/>
    <path class="mascot__wing mascot__wing--right" d="M100 70 C114 84 110 104 94 110 C98 96 96 84 88 74 Z"/>
    <ellipse class="mascot__belly" cx="60" cy="96" rx="26" ry="22"/>
    <path class="mascot__feathers" d="M48 92 q4 4 8 0 M64 92 q4 4 8 0 M56 102 q4 4 8 0"/>
    <circle class="mascot__socket" cx="42" cy="56" r="15"/>
    <circle class="mascot__socket" cx="78" cy="56" r="15"/>
    <path class="mascot__bridge" d="M57 55 Q60 51 63 55"/>
    <g class="mascot__look">
      <g class="mascot__pupil"><circle cx="42" cy="56" r="6"/><circle class="mascot__glint" cx="44" cy="54" r="2"/></g>
      <g class="mascot__pupil"><circle cx="78" cy="56" r="6"/><circle class="mascot__glint" cx="80" cy="54" r="2"/></g>
    </g>
    <path class="mascot__lids mascot__lids--happy" d="M33 59 Q42 49 51 59 M69 59 Q78 49 87 59"/>
    <path class="mascot__lids mascot__lids--sleep" d="M33 56 Q42 62 51 56 M69 56 Q78 62 87 56"/>
    <path class="mascot__beak" d="M52 70 L68 70 L60 84 Z"/>
    <path class="mascot__beak-open" d="M54 80 L66 80 L60 90 Z"/>
  </g>
  <g class="mascot__extra mascot__extra--thinking">
    <circle cx="100" cy="24" r="2.5"/><circle cx="108" cy="17" r="3"/><circle cx="116" cy="9" r="3.5"/>
  </g>
  <path class="mascot__extra mascot__extra--sleep" d="M100 20 h9 l-9 9 h9"/>
</svg>`;

/** Yer tutucunun içinə bayquşu çəkir (bir dəfə). Statik markap: istifadəçi
 *  mətni yoxdur. */
export function renderMascot(el) {
  if (!el.querySelector('svg')) el.innerHTML = SVG;
  el.setAttribute('aria-hidden', 'true');
  setMascotState(el, el.dataset.mascot);
  return el;
}

function placePupils(el, offsets) {
  el.querySelectorAll('.mascot__pupil').forEach((pupil, i) => {
    const o = offsets[i] || { x: 0, y: 0 };
    pupil.style.transform = `translate(${o.x.toFixed(2)}px, ${o.y.toFixed(2)}px)`;
  });
}

export function setMascotState(el, state) {
  const next = normalizeState(state);
  el.dataset.mascot = next;
  const fixed = FIXED_LOOK[next];
  if (fixed) placePupils(el, [fixed, fixed]);
  else if (next !== 'idle') placePupils(el, []);
  // Reaksiya animasiyasını yenidən başlat (eyni vəziyyət ard-arda gələndə).
  el.classList.remove('mascot--react');
  void el.offsetWidth;
  el.classList.add('mascot--react');
  return next;
}

/** Ekran koordinatında kursora görə hər iki bəbəyin yeri. */
export function lookAt(rect, pointer, viewBox = { width: 120, height: 130 }) {
  const scale = rect.width / viewBox.width;
  return EYES.map((eye) => {
    const cx = rect.left + eye.x * scale;
    const cy = rect.top + eye.y * scale;
    return pupilOffset(pointer.x - cx, pointer.y - cy);
  });
}

function canFollow(win) {
  if (!win.matchMedia) return false;
  return win.matchMedia('(hover: hover) and (pointer: fine)').matches
    && !win.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Masaüstündə bütün maskotların gözləri kursoru izləyir. Telefonda və
 *  «hərəkəti azalt»da heç nə qoşulmur. Dayandırmaq üçün funksiya qaytarır. */
export function followPointer(doc = document, win = window) {
  if (!canFollow(win)) return () => {};
  let pointer = null;
  let frame = 0;
  const update = () => {
    frame = 0;
    if (!pointer) return;
    doc.querySelectorAll('.mascot[data-mascot="idle"]').forEach((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > win.innerHeight) return;
      placePupils(el, lookAt(rect, pointer));
    });
  };
  const move = (event) => {
    pointer = { x: event.clientX, y: event.clientY };
    if (!frame) frame = win.requestAnimationFrame(update);
  };
  win.addEventListener('pointermove', move, { passive: true });
  return () => {
    win.removeEventListener('pointermove', move);
    if (frame) win.cancelAnimationFrame(frame);
  };
}

export function mountMascots(doc = document, win = window) {
  doc.querySelectorAll('[data-mascot]').forEach(renderMascot);
  return followPointer(doc, win);
}

/**
 * Boş siyahı: yatan bayquş + başlıq + izah (Faza 4). Əvvəl hər səhifə öz
 * `state__icon` ikonunu `innerHTML` ilə yazırdı. Mətn `textContent` ilə
 * gedir, bayquş dərhal çəkilir (ayrıca `mountMascots` lazım deyil).
 */
export function createEmptyState({ title, text = '', state = 'sleep' }, doc = document) {
  const box = doc.createElement('div');
  box.className = 'state';
  const mascot = doc.createElement('span');
  mascot.className = 'mascot state__mascot';
  mascot.dataset.mascot = state;
  renderMascot(mascot);
  const heading = doc.createElement('div');
  heading.className = 'state__title';
  heading.textContent = title;
  box.append(mascot, heading);
  if (text) {
    const hint = doc.createElement('div');
    hint.className = 'state__text';
    hint.textContent = text;
    box.append(hint);
  }
  return box;
}

/**
 * «AI hazırlayır» sətri: düşünən bayquş + izah (Faza 5). Sual bankı,
 * xülasə və AI yoxlaması fonda gedəndə müəllim boş gözləmir, kimin
 * işlədiyini görür. Mətn `textContent` ilə gedir.
 */
export function createThinking(text, doc = document) {
  const row = doc.createElement('div');
  row.className = 'thinking';
  const mascot = doc.createElement('span');
  mascot.className = 'mascot thinking__mascot';
  mascot.dataset.mascot = 'thinking';
  renderMascot(mascot);
  const line = doc.createElement('p');
  line.className = 'thinking__text';
  line.textContent = text;
  row.append(mascot, line);
  return row;
}
