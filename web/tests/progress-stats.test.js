import { test } from 'node:test';
import assert from 'node:assert/strict';

import { attendanceLine, hasProgressData, weekLabel } from '../assets/js/progress-stats.js';

test('hasProgressData false when both lists empty or missing', () => {
  assert.equal(hasProgressData({ weekly: [], by_subject: [] }), false);
  assert.equal(hasProgressData({}), false);
  assert.equal(hasProgressData(null), false);
});

test('hasProgressData true when either list has an entry', () => {
  assert.equal(hasProgressData({ weekly: [{ week_start: '2026-11-02' }], by_subject: [] }), true);
  assert.equal(hasProgressData({ weekly: [], by_subject: [{ subject: 'fizika' }] }), true);
});

test('weekLabel formats a 7-day range starting on the given date', () => {
  const label = weekLabel('2026-11-02');
  assert.match(label, /^02 .+ - 08 .+$/i);
});

test('attendanceLine says no finished lessons when percent is null', () => {
  assert.equal(attendanceLine({ attended: 0, total: 0, percent: null }), 'Hələ bitmiş dərs yoxdur.');
  assert.equal(attendanceLine(null), 'Hələ bitmiş dərs yoxdur.');
});

test('attendanceLine formats attended/total/percent', () => {
  assert.equal(attendanceLine({ attended: 3, total: 4, percent: 75 }), '3/4 dərsdə iştirak (75%)');
});
