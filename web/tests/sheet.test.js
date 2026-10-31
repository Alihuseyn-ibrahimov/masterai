import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { sheetKeyFromHash } from '../assets/js/sheet.js';

test('yalnız tanınan hash vərəq açır', () => {
  assert.equal(sheetKeyFromHash('#yeni', ['yeni', 'qosul']), 'yeni');
  assert.equal(sheetKeyFromHash('qosul', ['yeni', 'qosul']), 'qosul');
  assert.equal(sheetKeyFromHash('#quiz', ['yeni']), null);
  assert.equal(sheetKeyFromHash('', ['yeni']), null);
  assert.equal(sheetKeyFromHash(null, null), null);
});

test('vərəqli səhifələrdə forma <dialog class="sheet"> içindədir və bağla düyməsi var', () => {
  /* Siyahı-əvvəl qaydası: bu səhifələrdə forma birbaşa səhifədə qalsa,
     audit tapıntısı geri qayıdır. */
  const pages = { 'dersler.html': ['createForm'], 'hesabatlar.html': ['assignForm'],
    'chatlar.html': ['createForm', 'joinForm'] };
  for (const [page, forms] of Object.entries(pages)) {
    const html = readFileSync(new URL(`../${page}`, import.meta.url), 'utf8');
    const dialogs = [...html.matchAll(/<dialog class="sheet"[\s\S]*?<\/dialog>/g)].map((m) => m[0]);
    for (const form of forms) {
      assert.ok(dialogs.some((d) => d.includes(`id="${form}"`)), `${page}: ${form} vərəqdə deyil`);
    }
    for (const d of dialogs) {
      assert.ok(d.includes('data-sheet-close'), `${page}: bağla düyməsi yoxdur`);
      assert.match(d, /aria-labelledby="[^"]+"/, `${page}: vərəqin adı yoxdur`);
    }
  }
});

test('«Quiz yarat» forması istifadəçi qərarı ilə səhifədə açıq qalır', () => {
  const html = readFileSync(new URL('../muellim.html', import.meta.url), 'utf8');
  assert.match(html, /<details class="disclosure" id="createPanel" open>/);
});
