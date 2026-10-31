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
