import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  XP_PER_CORRECT, celebrationLevel, confettiPieces, countUp, finishMood,
} from '../assets/js/celebrate.js';
import { mascotLine } from '../assets/js/today.js';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

describe('yekun reaksiya', () => {
  test('səviyyə faizə görədir, məxrəcsiz nəticə bayram etmir', () => {
    assert.equal(celebrationLevel(4, 5), 'great');
    assert.equal(celebrationLevel(3, 5), 'good');
    assert.equal(celebrationLevel(1, 5), 'low');
    assert.equal(celebrationLevel(0, 0), 'none');
  });

  test('aşağı nəticədə bayquş sevinmir, amma təşviq edir', () => {
    assert.equal(finishMood('great').mascot, 'happy');
    assert.equal(finishMood('low').mascot, 'idle');
    assert.ok(finishMood('low').line.length > 0);
    assert.equal(finishMood('none').line, '');
  });

  test('XP «Bu gün» kartı ilə eyni qaydadır (1 düzgün = 10 XP)', () => {
    assert.equal(XP_PER_CORRECT, 10);
  });

  test('konfetti parçaları hər tərəfə səpələnir', () => {
    let seed = 1;
    const rng = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const pieces = confettiPieces(24, rng);
    assert.equal(pieces.length, 24);
    assert.ok(pieces.some((p) => p.x > 0) && pieces.some((p) => p.x < 0));
    for (const p of pieces) assert.match(p.color, /^var\(--/);
  });

  test('«hərəkəti azalt»da sayğac dərhal son rəqəmi yazır', () => {
    const el = { textContent: '' };
    const win = {
      matchMedia: () => ({ matches: true }),
      requestAnimationFrame: () => { throw new Error('animasiya olmamalıdır'); },
    };
    countUp(el, 7, { format: (n) => `${n}/9`, win });
    assert.equal(el.textContent, '7/9');
  });
});

describe('quiz ekranlarında bayquş', () => {
  for (const page of ['tapsiriq.html', 'sessiya.html', 'qosul.html']) {
    test(`${page}: nəticədə və bitişdə bayquş var`, () => {
      const html = read(`../${page}`);
      assert.match(html, /id="verdictMascot"/);
      assert.match(html, /id="finishMascot"/);
      assert.match(html, /id="finishLine"/);
    });
  }

  test('qonaq ekranında XP göstərilmir (nəticə tarixçəyə düşmür)', () => {
    const html = read('../qosul.html');
    assert.doesNotMatch(html, /id="xpPop"|id="finishXp"/);
    assert.match(read('../tapsiriq.html'), /id="xpPop"/);
  });

  test('boş siyahılar yatan bayquşu ortaq köməkçi ilə çəkir', () => {
    for (const page of ['tapsiriqlar.html', 'tarixce.html', 'xulaseler.html', 'dersler.html', 'chatlar.html']) {
      const html = read(`../${page}`);
      assert.match(html, /createEmptyState\(/, page);
      assert.doesNotMatch(html, /state__icon/, page);
    }
  });
});

describe('«Bu gün» bayquşunun cümləsi', () => {
  test('bu gün XP qazanılıbsa sevinir', () => {
    assert.deepEqual(mascotLine({ todayXp: 30 }), { state: 'happy', text: 'Bu gün +30 XP. Əla gedirsən!' });
  });

  test('XP yoxdursa gözləyən tapşırığı xatırladır, uzun ad kəsilir', () => {
    const line = mascotLine({ next: { title: 'A'.repeat(80) } });
    assert.equal(line.state, 'idle');
    assert.ok(line.text.length < 60);
    assert.match(line.text, /…» səni gözləyir\.$/);
  });

  test('sonra seriya, sonra ümumi sual; müəllimə ayrıca cümlə', () => {
    assert.match(mascotLine({ streak: 3 }).text, /^3 günlük seriya/);
    assert.equal(mascotLine({}).text, 'Bu gün nə öyrənirik?');
    assert.match(mascotLine({ isTeacher: true, todayXp: 50 }).text, /konspekt və quizi/);
  });
});
