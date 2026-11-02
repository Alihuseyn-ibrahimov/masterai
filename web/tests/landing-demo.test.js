import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  CLASS_SIZE, DEMO_QUESTIONS, HEADLINE_WORDS, answeredText, demoTimeline, nextWord, streakText,
} from '../assets/js/landing-demo.js';
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');

describe('başlıqda dəyişən söz', () => {
  test('dövrəvi gedir və statik HTML sözündən başlayır', () => {
    assert.equal(HEADLINE_WORDS[0], 'qalanını');
    assert.match(html, /<span class="sr-only">qalanını<\/span><span class="rotator__word" data-rotator aria-hidden="true">qalanını<\/span>/);
    assert.equal(nextWord(HEADLINE_WORDS, 'qalanını'), 'konspekti');
    assert.equal(nextWord(HEADLINE_WORDS, 'davamiyyəti'), 'qalanını');
  });
});

describe('hero sual demosu', () => {
  test('cədvəl sıralıdır, sinif sayını aşmır və «gözlənilir» düzgündən əvvəldir', () => {
    const t = demoTimeline();
    for (let i = 1; i < t.length; i++) {
      assert.ok(t[i].at > t[i - 1].at);
      assert.ok(t[i].answered >= t[i - 1].answered);
      assert.ok(t[i].answered <= CLASS_SIZE);
    }
    const phases = t.map((m) => m.phase);
    assert.ok(phases.indexOf('chosen') < phases.indexOf('correct'));
    assert.equal(phases.at(-1), 'next');
  });

  test('hər sualda 3 variant var, düzgün indeks keçərlidir', () => {
    for (const q of DEMO_QUESTIONS) {
      assert.equal(q.options.length, 3);
      assert.ok(q.correct >= 0 && q.correct < 3);
    }
  });

  test('statik HTML birinci demo sualı və son cədvəl anı ilə üst-üstə düşür', () => {
    /* JS-siz və «hərəkəti azalt» rejimində görünən vəziyyət demonun öz
       ilk kadrıdır - dövrə başlayanda sıçrayış olmur. */
    const first = DEMO_QUESTIONS[0];
    assert.ok(html.includes(first.prompt));
    first.options.forEach((option) => assert.ok(html.includes(option)));
    const settled = demoTimeline().at(-2);
    assert.ok(html.includes(answeredText(settled.answered)));
    assert.ok(html.includes(streakText(3)));
  });
});
