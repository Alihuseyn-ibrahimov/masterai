import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  contentError, contentFromForm, linesToList, linesToPairs, listToLines, pairsToLines,
} from '../assets/js/summary.js';

test('lines ignore blanks and bullet marks', () => {
  assert.deepEqual(linesToList('- bir\n\n• iki \n*üç'), ['bir', 'iki', 'üç']);
  assert.equal(listToLines(['a', 'b']), 'a\nb');
});

test('pairs round-trip, a dash inside the definition stays there', () => {
  const pairs = [{ term: 'Referendum', definition: 'Ümumxalq səsverməsi - qanun üzrə.' }];
  const text = pairsToLines(pairs, 'term', 'definition');
  assert.deepEqual(linesToPairs(text, 'term', 'definition'), pairs);
});

test('lines without separator are kept', () => {
  assert.deepEqual(linesToPairs('Neçə qol? - Üç\nTək sətir', 'question', 'answer'), [
    { question: 'Neçə qol?', answer: 'Üç' },
    { question: 'Tək sətir', answer: '' },
  ]);
});

test('hyphenated word is not split', () => {
  assert.deepEqual(linesToPairs('Qeyri-hökumət - təşkilat', 'term', 'definition'),
    [{ term: 'Qeyri-hökumət', definition: 'təşkilat' }]);
});

test('form values become the API body and are validated', () => {
  const content = contentFromForm({
    title: ' Başlıq ', intro: 'Giriş', keyPoints: 'a\nb', terms: '', facts: '', selfCheck: '',
  });
  assert.equal(content.title, 'Başlıq');
  assert.deepEqual(content.key_points, ['a', 'b']);
  assert.equal(contentError(content), null);
  assert.match(contentError({ ...content, key_points: ['a'] }), /2 əsas fikir/);
  assert.match(contentError({ ...content, title: '' }), /Başlıq/);
});
