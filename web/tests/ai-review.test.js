import test from 'node:test';
import assert from 'node:assert/strict';
import { reviewByQuestion, reviewStatusLine, suggestionPatch, verdictBadge } from '../assets/js/ai-review.js';

test('reviewByQuestion maps by id and tolerates empty', () => {
  assert.equal(reviewByQuestion(null).size, 0);
  const map = reviewByQuestion({ items: [{ question_id: 7, verdict: 'ok' }] });
  assert.equal(map.get(7).verdict, 'ok');
});

test('verdictBadge: unchecked is never shown as ok', () => {
  assert.match(verdictBadge('ok').className, /success/);
  assert.match(verdictBadge('fix').className, /warning/);
  assert.equal(verdictBadge('unchecked').label, 'AI: yoxlanmadı');
});

test('reviewStatusLine per status', () => {
  assert.match(reviewStatusLine({ status: 'processing' }, 3), /yoxlayır/);
  assert.match(reviewStatusLine({ status: 'failed', error: 'Groq' }, 3), /Groq/);
  assert.match(reviewStatusLine(null, 3), /fakt yoxlayıcı/);
  const line = reviewStatusLine({ status: 'ready', items: [{ verdict: 'ok' }, { verdict: 'fix' }] }, 3);
  assert.equal(line, 'AI yoxlaması: 1 sual qaydasındadır · 1 suala baxmaq lazımdır · 1 sual yoxlanmayıb və ya sonra dəyişdirilib.');
});

test('suggestionPatch keeps difficulty and five options', () => {
  const body = suggestionPatch({ question: 'S', options: ['a', 'b', 'c', 'd', 'e'], correct_index: 3 }, 'çətin');
  assert.deepEqual(body, { question: 'S', options: ['a', 'b', 'c', 'd', 'e'], correct_index: 3, explanation: '', difficulty: 'çətin' });
  assert.equal('difficulty' in suggestionPatch({ question: 'S', options: [], correct_index: 0 }, null), false);
});

test('reviewStatusLine hides zero fix count', () => {
  assert.equal(reviewStatusLine({ status: 'ready', items: [{ verdict: 'ok' }] }, 1), 'AI yoxlaması: 1 sual qaydasındadır.');
});
