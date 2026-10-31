import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  TABS, initialTab, lessonPrimaryAction, lessonStatusNote, nextTabKey,
  openQuizCount, visibleTabs,
} from '../assets/js/lesson-tabs.js';

describe('visibleTabs', () => {
  test('«Mətn» yalnız müəllimdədir', () => {
    assert.deepEqual(visibleTabs(false).map((t) => t.key), ['summary', 'quiz', 'note', 'tutor']);
    assert.ok(visibleTabs(true).some((t) => t.key === 'text'));
  });

  test('hər tab ikonu sprite-da var', () => {
    const sprite = readFileSync(new URL('../assets/icons.svg', import.meta.url), 'utf8');
    for (const tab of TABS) assert.ok(sprite.includes(`id="i-${tab.icon}"`), tab.icon);
  });
});

describe('initialTab', () => {
  const open = [{ status: 'gözləyir' }];
  const done = [{ status: 'tamamlanıb' }];

  test('linkdəki keçərli tab üstündür', () => {
    assert.equal(initialTab({ hash: '#note', isTeacher: false, assignments: open }), 'note');
  });

  test('tələbə üçün «Mətn» linki keçərsizdir', () => {
    assert.equal(initialTab({ hash: '#text', isTeacher: false, summary: null, assignments: [] }), 'note');
  });

  test('bitməmiş quiz tələbəni Quiz-ə aparır', () => {
    assert.equal(initialTab({ hash: '', isTeacher: false, summary: { id: 1 }, assignments: open }), 'quiz');
  });

  test('quiz bitibsə konspekt', () => {
    assert.equal(initialTab({ hash: '', isTeacher: false, summary: { id: 1 }, assignments: done }), 'summary');
  });

  test('heç nə yoxdursa tələbədə Qeydim, müəllimdə Mətn', () => {
    assert.equal(initialTab({ hash: '', isTeacher: false, summary: null, assignments: [] }), 'note');
    assert.equal(initialTab({ hash: '', isTeacher: true, summary: null, assignments: open }), 'text');
  });
});

describe('openQuizCount', () => {
  test('yalnız bitirilməmişlər', () => {
    assert.equal(openQuizCount([{ status: 'gözləyir' }, { status: 'davam edir' }, { status: 'tamamlanıb' }]), 2);
    assert.equal(openQuizCount(null), 0);
  });
});

describe('nextTabKey', () => {
  const keys = ['a', 'b', 'c'];
  test('oxlar dövri keçir, Home/End kənarlara', () => {
    assert.equal(nextTabKey(keys, 'c', 'ArrowRight'), 'a');
    assert.equal(nextTabKey(keys, 'a', 'ArrowLeft'), 'c');
    assert.equal(nextTabKey(keys, 'b', 'Home'), 'a');
    assert.equal(nextTabKey(keys, 'b', 'End'), 'c');
    assert.equal(nextTabKey(keys, 'b', 'Enter'), null);
    assert.equal(nextTabKey(keys, 'x', 'ArrowRight'), null);
  });
});

describe('lessonPrimaryAction', () => {
  test('yalnız canlı onlayn dərs otağa aparır', () => {
    /* Auditdə tapılıb: planlaşdırılmış dərsdə «Dərs otağı» görünürdü. */
    assert.deepEqual(lessonPrimaryAction({ id: 5, mode: 'online', status: 'live' }),
      { label: 'Dərsə qoşul', href: 'dars.html?id=5' });
    assert.equal(lessonPrimaryAction({ id: 5, mode: 'online', status: 'scheduled' }), null);
    assert.equal(lessonPrimaryAction({ id: 5, mode: 'online', status: 'ended' }), null);
    assert.equal(lessonPrimaryAction({ id: 5, mode: 'offline', status: 'live' }), null);
    assert.equal(lessonPrimaryAction(null), null);
  });
});

describe('lessonStatusNote', () => {
  test('vəziyyətə və rola görə', () => {
    assert.match(lessonStatusNote({ status: 'scheduled', mode: 'online' }, false), /Dərsə qoşul/);
    assert.match(lessonStatusNote({ status: 'scheduled', mode: 'offline' }, false), /QR/);
    assert.match(lessonStatusNote({ status: 'ended' }, true), /tələbələrə göndərin/);
    assert.match(lessonStatusNote({ status: 'ended' }, false), /müəllim paylaşanda/);
    // Render-də tapılıb: quiz artıq verilmişdi, mətn isə «paylaşanda» deyirdi.
    assert.match(lessonStatusNote({ status: 'ended' }, false, true), /aşağıdadır/);
    assert.equal(lessonStatusNote({ status: 'live', mode: 'online' }, false), '');
  });
});
