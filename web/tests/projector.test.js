import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  classProgress, displayUrl, formatPin, podium, stagePhase, visibleNames,
} from '../assets/js/projector.js';

test('PIN üç-üç bölünür, səhv uzunluq toxunulmur', () => {
  assert.equal(formatPin('123456'), '123 456');
  assert.equal(formatPin('12 34 56'), '123 456');
  assert.equal(formatPin('1234'), '1234');
  assert.equal(formatPin(null), '');
});

test('ekrandakı link sxemsiz və PIN-siz qısa yazılır', () => {
  assert.equal(displayUrl('https://masterai.prdostu.com/qosul.html?pin=123456'),
    'masterai.prdostu.com/qosul.html');
});

test('mərhələ: gözləmə → gedişat → nəticə', () => {
  assert.equal(stagePhase({ started: false, finished: false }), 'waiting');
  assert.equal(stagePhase({ started: true, finished: false }), 'running');
  assert.equal(stagePhase({ started: true, finished: true }), 'finished');
});

test('sinfin gedişatı: cəm faiz və bitirənlər, artıq cavab sayılmır', () => {
  const rows = [
    { name: 'Aysel', answered: 4, total: 4, finished: true },
    { name: 'Murad', answered: 2, total: 4, finished: false },
    { name: 'Nigar', answered: 9, total: 4, finished: true },
  ];
  assert.deepEqual(classProgress(rows), {
    people: 3, finished: 2, finishedNames: ['Aysel', 'Nigar'], percent: 83,
  });
  assert.deepEqual(classProgress([]), { people: 0, finished: 0, finishedNames: [], percent: 0 });
});

test('uzun ad siyahısı kəsilir, qalanı sayılır', () => {
  assert.deepEqual(visibleNames(['a', 'b', 'c'], 5), { shown: ['a', 'b', 'c'], more: 0 });
  assert.deepEqual(visibleNames(['a', 'b', 'c'], 2), { shown: ['a', 'b'], more: 1 });
});

test('podium 2-1-3 sırası ilə, bərabər xal eyni yer', () => {
  const result = podium([
    { display_name: 'Aysel', correct_count: 5 },
    { display_name: 'Murad', correct_count: 5 },
    { display_name: 'Nigar', correct_count: 3 },
    { participant_id: 9, score: 1 },
  ]);
  assert.deepEqual(result.podium.map((r) => [r.name, r.place]),
    [['Murad', 1], ['Aysel', 1], ['Nigar', 3]]);
  assert.deepEqual(result.rest, [{ name: 'İştirakçı #9', score: 1, place: 4 }]);
});

test('podium bir iştirakçı ilə də işləyir', () => {
  assert.deepEqual(podium([{ display_name: 'Tək', correct_count: 2 }]).podium.map((r) => r.name), ['Tək']);
  assert.deepEqual(podium([]), { podium: [], rest: [] });
});

test('konsol proyektor ekranını qurur və gedişatda fərdi xal göstərmir', () => {
  const html = readFileSync(new URL('../sessiyalar.html', import.meta.url), 'utf8');
  assert.match(html, /id="projectorButton"/);
  assert.match(html, /<section class="stage" id="stage"/);
  assert.match(html, /from '\.\/assets\/js\/projector\.js'/);
  assert.match(html, /\/join-qr`/);
});
