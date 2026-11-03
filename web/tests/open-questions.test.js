import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  countError, kindLabel, linesToRubric, maxPoints, rubricToLines, setSummaryLine,
} from '../assets/js/open-questions.js';

const RUBRIC = [{ points: 2, criterion: 'Orqanı göstərir' }, { points: 3, criterion: 'Proseduru izah edir' }];

test('rubric round-trips through text lines', () => {
  const text = rubricToLines(RUBRIC);
  assert.equal(text, '2 | Orqanı göstərir\n3 | Proseduru izah edir');
  assert.deepEqual(linesToRubric(`${text}\n\n`).rubric, RUBRIC);
});

test('linesToRubric explains what is wrong', () => {
  assert.match(linesToRubric('').error, /bir meyar/);
  assert.match(linesToRubric('Orqanı göstərir').error, /1-ci sətir/);
  assert.match(linesToRubric('2 | a\n9 | b').error, /2-ci sətir: bal 1 ilə 5/);
  assert.match(linesToRubric('1 | a\n'.repeat(7)).error, /ən çox 6/i);
  assert.deepEqual(linesToRubric('  4|  Səbəbi izah edir ').rubric, [{ points: 4, criterion: 'Səbəbi izah edir' }]);
});

test('points and labels', () => {
  assert.equal(maxPoints(RUBRIC), 5);
  assert.equal(maxPoints(null), 0);
  assert.equal(kindLabel('qisa'), 'Qısa cavab');
  assert.equal(kindLabel('esse'), 'Esse');
});

test('setSummaryLine', () => {
  assert.equal(setSummaryLine([]), '');
  const items = [{ kind: 'qisa', max_points: 3 }, { kind: 'qisa', max_points: 2 }, { kind: 'esse', rubric: RUBRIC }];
  assert.equal(setSummaryLine(items), '3 sual · 2 qısa cavab, 1 esse · cəmi 10 bal');
  assert.equal(setSummaryLine([{ kind: 'esse', max_points: 4 }]), '1 sual · 1 esse · cəmi 4 bal');
});

test('countError', () => {
  assert.equal(countError('5'), null);
  assert.ok(countError('0'));
  assert.ok(countError('16'));
  assert.ok(countError('2.5'));
});
