import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  EYES, MASCOT_STATES, PUPIL_RANGE, lookAt, normalizeState, pupilOffset,
} from '../assets/js/mascot.js';

const css = readFileSync(new URL('../assets/css/components.css', import.meta.url), 'utf8');

describe('bəbəyin hərəkəti', () => {
  test('kursor göz mərkəzindədirsə bəbək yerindən tərpənmir', () => {
    assert.deepEqual(pupilOffset(0, 0), { x: 0, y: 0 });
  });

  test('istiqamət kursora doğrudur', () => {
    const right = pupilOffset(500, 0);
    assert.ok(right.x > 0 && Math.abs(right.y) < 1e-9);
    const up = pupilOffset(0, -500);
    assert.ok(up.y < 0 && Math.abs(up.x) < 1e-9);
  });

  test('uzaq kursorda radiusu aşmır, yaxında az tərpənir', () => {
    const far = pupilOffset(3000, 4000);
    assert.ok(Math.abs(Math.hypot(far.x, far.y) - PUPIL_RANGE) < 1e-9);
    const near = pupilOffset(24, 0);
    assert.ok(near.x > 0 && near.x < PUPIL_RANGE / 2);
  });

  test('iki göz ayrı hesablanır: aralarındakı kursora hər ikisi içəri baxır', () => {
    // 120 vahidlik viewBox 120 px-ə çəkilib, kursor iki gözün tam ortasında.
    const rect = { left: 0, top: 0, width: 120, height: 130 };
    const mid = { x: (EYES[0].x + EYES[1].x) / 2, y: EYES[0].y };
    const [left, right] = lookAt(rect, mid);
    assert.ok(left.x > 0, 'sol göz sağa baxır');
    assert.ok(right.x < 0, 'sağ göz sola baxır');
  });
});

describe('vəziyyətlər', () => {
  test('naməlum vəziyyət «gözləyir» olur', () => {
    assert.equal(normalizeState('dance'), 'idle');
    assert.equal(normalizeState(undefined), 'idle');
    for (const state of MASCOT_STATES) assert.equal(normalizeState(state), state);
  });

  test('hər vəziyyətin CSS-də öz görünüşü var', () => {
    for (const state of MASCOT_STATES.filter((s) => s !== 'idle')) {
      assert.ok(css.includes(`.mascot[data-mascot="${state}"]`) || css.includes(`[data-mascot="${state}"]`),
        `${state} üçün CSS yoxdur`);
    }
  });

  test('«hərəkəti azalt»da maskot animasiyası söndürülür', () => {
    const block = css.slice(css.indexOf('/* ---- Maskot'));
    assert.match(block, /prefers-reduced-motion: reduce\)\s*\{\s*\.mascot \*/);
  });
});
