import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  answerStatusLine, countError, criterionLine, kindLabel, linesToRubric, maxPoints, pointsError, rubricToLines,
  setSummaryLine, suggestedPoints,
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

test('answerStatusLine per status and audience', () => {
  const base = { max_points: 5, ai_points: 3, final_points: null };
  assert.equal(answerStatusLine(null), '');
  assert.equal(answerStatusLine({ ...base, status: 'grading' }), 'AI cavabı yoxlayır…');
  assert.match(answerStatusLine({ ...base, status: 'graded' }), /3\/5 bal\. Yekun balı müəllim/);
  assert.equal(answerStatusLine({ ...base, status: 'graded' }, 'teacher'), 'AI təklifi: 3/5 bal · təsdiq gözləyir');
  assert.match(answerStatusLine({ ...base, status: 'failed' }), /müəllim özü yoxlayacaq/);
  assert.equal(answerStatusLine({ ...base, status: 'confirmed', final_points: 4 }), 'Yekun bal: 4/5');
});

test('criterionLine, suggestedPoints, pointsError', () => {
  assert.equal(criterionLine({ criterion: 'DİM', awarded: 1, points: 2, comment: 'qismən' }), 'DİM: 1/2 bal - qismən');
  assert.equal(criterionLine({ criterion: 'DİM', awarded: 2, points: 2, comment: '' }), 'DİM: 2/2 bal');
  assert.equal(suggestedPoints({ ai_points: 3, final_points: null }), '3');
  assert.equal(suggestedPoints({ ai_points: 3, final_points: 0 }), '0');
  assert.equal(suggestedPoints({ ai_points: null, final_points: null }), '');
  assert.equal(pointsError('4', 5), null);
  assert.ok(pointsError('6', 5));
  assert.ok(pointsError('', 5));
  assert.ok(pointsError('1.5', 5));
});
