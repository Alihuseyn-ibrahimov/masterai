import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ordinal, sourceNote, splitSteps, stepMark, verdictOf } from '../assets/js/diagnose.js';

test('ordinal uses Azerbaijani vowel harmony', () => {
  assert.deepEqual([1, 2, 3, 4, 6, 9, 10, 13].map(ordinal),
    ['1-ci', '2-ci', '3-cü', '4-cü', '6-cı', '9-cu', '10-cu', '13-cü']);
});

test('verdict never turns "unknown" into "correct"', () => {
  assert.equal(verdictOf({ status: 'unknown' }).tone, 'unknown');
  assert.equal(verdictOf({ status: 'correct' }).tone, 'correct');
  const wrong = verdictOf({ status: 'error_found', wrong_step: 3, error_name: 'Hesablama səhvi' });
  assert.deepEqual(wrong, { title: '3-cü addımda səhv: Hesablama səhvi', tone: 'wrong' });
  assert.equal(verdictOf({ status: 'error_found', wrong_step: 2, error_name: null }).title, '2-ci addımda səhv');
});

test('model-only error is presented as a suggestion', () => {
  assert.match(sourceNote({ source: 'model', status: 'error_found' }), /özünüz yoxlayın/);
  assert.match(sourceNote({ source: 'model+sympy', agreement: false }), /düzəltdi/);
  assert.match(sourceNote({ source: 'none', model_error: 'model cavab vermədi' }), /cavab vermədi/);
  assert.match(sourceNote({ source: 'none' }), /AI model qoşulmalıdır/);
});

test('step marks and splitting', () => {
  assert.equal(stepMark({ status: 'ok' }), null);
  assert.equal(stepMark({ status: 'wrong' }).badge, 'badge--danger');
  assert.deepEqual(splitSteps(' 1) 2 + 2 \n\n = 4 \n'), ['1) 2 + 2', '= 4']);
  // bir sətirdə « / » ilə yazılmış həll bölünür, «1/2» isə yox
  assert.deepEqual(splitSteps('A həyvandır / B həyvandır / Deməli, B A-dır'),
    ['A həyvandır', 'B həyvandır', 'Deməli, B A-dır']);
  assert.deepEqual(splitSteps('1/2 + 1/3'), ['1/2 + 1/3']);
});
