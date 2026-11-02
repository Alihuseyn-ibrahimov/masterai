/* Quiz ekranlarının reaksiyası: bayquş, «+10 XP», xalın sayılması,
 * konfetti (2026-11-02, «Dəftər + maskot» Faza 4).
 *
 * NİYƏ AYRICA MODUL: üç quiz ekranı var (ev tapşırığı, canlı sessiya,
 * PIN ilə qonaq). Reaksiya hər birində ayrı yazılsa, keçmişdəki kimi
 * (variant çəkilişi, geri bildirim) biri yenilənib digəri köhnə qalardı.
 *
 * Qayda: hərəkət yalnız bəzəkdir. Mənanı «Düzgün»/«Səhv» mətni və xal
 * verir; «hərəkəti azalt»da sayğac dərhal son rəqəmi yazır, konfetti
 * ümumiyyətlə çəkilmir.
 */

import { setMascotState } from './mascot.js';
/* XP qaydası «Bu gün» kartının qaydasıdır: quizdə görünən «+10 XP» ilə
 * «Bu gün XP» eyni mənbədən gəlir. */
import { XP_PER_CORRECT } from './today.js';

export { XP_PER_CORRECT };

/** Yekun faizə görə səviyyə: 80%+ bayram (konfetti), 50%+ sevinc,
 *  aşağısı sakit təşviq. Məxrəc yoxdursa səviyyə də yoxdur. */
export function celebrationLevel(correct, total) {
  if (!total) return 'none';
  const pct = (correct / total) * 100;
  if (pct >= 80) return 'great';
  if (pct >= 50) return 'good';
  return 'low';
}

/** Səviyyəyə görə bayquşun vəziyyəti və altındakı cümlə. */
export function finishMood(level) {
  if (level === 'great') return { mascot: 'happy', line: 'Əla nəticə!' };
  if (level === 'good') return { mascot: 'happy', line: 'Yaxşı iş. Səhvlərin izahını bir də oxu.' };
  if (level === 'low') return { mascot: 'idle', line: 'Bu mövzunu təkrarla, növbəti dəfə daha yaxşı olacaq.' };
  return { mascot: 'idle', line: '' };
}

export function prefersReducedMotion(win = globalThis.window) {
  return Boolean(win && win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

/** Cavabdan sonra: bayquş sevinir və ya təəccüblənir, düzgündə «+10 XP»
 *  çipi yenidən «atılır». Element tapılmasa sükutla keçir (qonaq ekranında
 *  XP çipi yoxdur: qonağın nəticəsi tarixçəyə düşmür). */
export function reactToAnswer(root, isCorrect) {
  const mascot = root.getElementById('verdictMascot');
  if (mascot) setMascotState(mascot, isCorrect ? 'happy' : 'surprised');
  const xp = root.getElementById('xpPop');
  if (xp) {
    xp.hidden = !isCorrect;
    xp.textContent = `+${XP_PER_CORRECT} XP`;
    xp.classList.remove('xp-pop--go');
    if (isCorrect) {
      void xp.offsetWidth;
      xp.classList.add('xp-pop--go');
    }
  }
}

/** Rəqəmi 0-dan `to`-ya sayır (ease-out). «Hərəkəti azalt»da və ya
 *  `requestAnimationFrame` yoxdursa dərhal son mətni yazır. */
export function countUp(el, to, { format = String, duration = 900, win = globalThis.window } = {}) {
  if (!el) return;
  const raf = win && win.requestAnimationFrame;
  if (!raf || prefersReducedMotion(win) || to <= 0) {
    el.textContent = format(to);
    return;
  }
  const start = win.performance ? win.performance.now() : Date.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - (1 - t) ** 3;
    el.textContent = format(Math.round(to * eased));
    if (t < 1) raf.call(win, step);
  };
  el.textContent = format(0);
  raf.call(win, step);
}

const CONFETTI_COLORS = ['var(--opt-a)', 'var(--opt-b)', 'var(--opt-c)', 'var(--opt-d)', 'var(--opt-e)', 'var(--color-accent)'];

/** Konfetti parçalarının parametrləri (saf funksiya, testlənir). `rng`
 *  0-1 arası ədəd verir. Parçalar mərkəzdən hər tərəfə səpələnir. */
export function confettiPieces(count = 24, rng = Math.random) {
  return Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2 + rng() * 0.5;
    const distance = 90 + rng() * 80;
    return {
      x: Math.round(Math.cos(angle) * distance),
      y: Math.round(Math.sin(angle) * distance - 40),
      rotate: Math.round(rng() * 720 - 360),
      color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
    };
  });
}

/** Elementin üstündə bir dəfəlik konfetti partlayışı; 1.6 saniyədən
 *  sonra özü silinir. «Hərəkəti azalt»da heç nə çəkilmir. */
export function burstConfetti(host, { win = globalThis.window, count = 24 } = {}) {
  if (!host || prefersReducedMotion(win)) return null;
  const doc = host.ownerDocument;
  const layer = doc.createElement('span');
  layer.className = 'confetti';
  layer.setAttribute('aria-hidden', 'true');
  for (const piece of confettiPieces(count)) {
    const bit = doc.createElement('span');
    bit.className = 'confetti__bit';
    bit.style.setProperty('--cx', `${piece.x}px`);
    bit.style.setProperty('--cy', `${piece.y}px`);
    bit.style.setProperty('--cr', `${piece.rotate}deg`);
    bit.style.setProperty('--opt', piece.color);
    layer.append(bit);
  }
  host.append(layer);
  setTimeout(() => layer.remove(), 1600);
  return layer;
}

/** Yekun kart: xal sayılır, bayquş səviyyəyə görə reaksiya verir,
 *  80%+ nəticədə konfetti. `ids` - kartdakı elementlərin ID-ləri. */
export function celebrateFinish(root, correct, total) {
  const level = celebrationLevel(correct, total);
  const mood = finishMood(level);
  const mascot = root.getElementById('finishMascot');
  if (mascot) setMascotState(mascot, mood.mascot);
  const line = root.getElementById('finishLine');
  if (line) {
    line.textContent = mood.line;
    line.hidden = !mood.line;
  }
  if (total) {
    countUp(root.getElementById('scoreRingValue'), correct, { format: (n) => `${n}/${total}` });
  }
  const xp = root.getElementById('finishXp');
  if (xp) {
    xp.hidden = !(total && correct);
    countUp(xp, correct * XP_PER_CORRECT, { format: (n) => `+${n} XP` });
  }
  if (level === 'great') burstConfetti(root.getElementById('scoreRing'));
  return level;
}
