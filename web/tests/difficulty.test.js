import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAULT_MIX, countLevels, levelBadgeClass, levelLabel, mixError, parseMix, summaryLine,
} from '../assets/js/difficulty.js';

test('default mix sums to 100', () => {
  assert.equal(mixError(DEFAULT_MIX), null);
});

test('mixError catches wrong sum and bad numbers', () => {
  assert.match(mixError([50, 50, 10]), /indi 110/);
  assert.ok(mixError([-10, 60, 50]));
  assert.match(mixError(['', '50', '50']), /tam ədəd/);
  assert.ok(mixError([33.5, 33.5, 33]));
  assert.equal(mixError(['20', '50', '30']), null);
});

test('parseMix', () => {
  assert.deepEqual(parseMix('20/50/30'), [20, 50, 30]);
  assert.equal(parseMix(null), null);
  assert.equal(parseMix('10/10'), null);
  assert.equal(parseMix('50/50/50'), null);
});

test('summaryLine counts levels and shows requested mix', () => {
  const qs = [{ difficulty: 'asan' }, { difficulty: 'orta' }, { difficulty: 'orta' }, { difficulty: 'çətin' }];
  assert.equal(summaryLine(qs, '30/50/20'), '1 asan · 2 orta · 1 çətin (istənilən 30/50/20)');
});

test('old questions without level are counted separately, old bank has no mix', () => {
  const qs = [{ difficulty: null }, { difficulty: 'asan' }];
  assert.deepEqual(countLevels(qs), { asan: 1, orta: 0, 'çətin': 0, none: 1 });
  assert.equal(summaryLine(qs, null), '1 asan · 0 orta · 0 çətin · 1 səviyyəsiz');
});

test('labels and badge classes', () => {
  assert.equal(levelLabel('çətin'), 'Çətin');
  assert.equal(levelLabel(null), 'Səviyyəsiz');
  assert.equal(levelBadgeClass('asan'), 'badge badge--info');
  assert.equal(levelBadgeClass(undefined), 'text-xs text-faint');
});
