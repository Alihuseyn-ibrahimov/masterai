import test from 'node:test';
import assert from 'node:assert/strict';
import { sourceHref, splitCitations } from '../assets/js/tutor.js';

test('istinadlar mətndən ayrılır', () => {
  assert.deepEqual(splitCitations('1995-ci ildə [1], referendumla [2].'), [
    { text: '1995-ci ildə ' }, { cite: 1 }, { text: ', referendumla ' }, { cite: 2 }, { text: '.' },
  ]);
  assert.deepEqual(splitCitations('İstinadsız'), [{ text: 'İstinadsız' }]);
  assert.deepEqual(splitCitations(''), []);
});

test('mənbə linki', () => {
  assert.equal(sourceHref({ lesson_id: 4 }), 'dersim.html?id=4');
  assert.equal(sourceHref({ summary_id: 9 }), 'xulase.html?id=9');
  assert.equal(sourceHref({ title: 'x' }), null);
});

import { HISTORY_LIMIT, pushTurn, tutorTurnText } from '../assets/js/tutor.js';

test('pushTurn keeps only the last turns and skips empty text', () => {
  let history = [];
  for (let i = 0; i < 10; i += 1) history = pushTurn(history, i % 2 ? 'tutor' : 'user', `t${i}`);
  assert.equal(history.length, HISTORY_LIMIT);
  assert.equal(history[0].text, 't4');
  assert.equal(pushTurn(history, 'tutor', '  ').length, HISTORY_LIMIT);
});

test('tutorTurnText per reply kind', () => {
  assert.equal(tutorTurnText({ kind: 'answer', answer: 'Cavab [1].' }), 'Cavab [1].');
  assert.equal(tutorTurnText({ kind: 'quiz', quiz: { question: 'Nə vaxt?' } }), 'Test sualı: Nə vaxt?');
  assert.equal(tutorTurnText({ kind: 'not_found', answer: '' }), '');
});
