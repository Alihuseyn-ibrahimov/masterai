import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  contentError, contentFromForm, linesToList, linesToPairs, listToLines, pairsToLines,
  readingMinutes, summaryStats,
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

test('kart göstəriciləri boş hissəni yazmır', () => {
  const content = { key_points: ['a', 'b', 'c'], terms: [], self_check: [{ question: 'q', answer: 'a' }] };
  assert.equal(summaryStats(content), '3 əsas fikir · 1 sual');
  assert.equal(summaryStats(null), '');
});

test('oxuma müddəti ən az 1 dəqiqədir və söz sayı ilə artır', () => {
  assert.equal(readingMinutes({ title: 'x', intro: 'qısa', key_points: [] }), 1);
  const long = { title: 't', intro: '', key_points: [Array(720).fill('söz').join(' ')] };
  assert.equal(readingMinutes(long), 4);
  assert.equal(readingMinutes(null), 1);
});
