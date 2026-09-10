import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

import { deadlineNote, sortByUrgency } from '../assets/js/deadline.js';

// Sabit "bugün": test saatdan asılı olmamalıdır.
const TODAY = '2026-09-10';

describe('son tarix mətni', () => {
  test('bugün son gündür', () => {
    const note = deadlineNote('2026-09-10', TODAY);
    assert.equal(note.label, 'Bugün son gün');
    assert.equal(note.className, 'badge badge--danger');
  });

  test('sabah', () => {
    assert.equal(deadlineNote('2026-09-11', TODAY).label, 'Sabah son gün');
  });

  test('bir neçə gün qalıb', () => {
    assert.equal(deadlineNote('2026-09-15', TODAY).label, '5 gün qalıb');
  });

  test('gecikmə açıq deyilir', () => {
    // "son tarix: 2026-09-05" tələbəyə heç nə demir; "2 gün gecikib" deyir.
    const note = deadlineNote('2026-09-08', TODAY);
    assert.equal(note.label, '2 gün gecikib');
    assert.equal(note.className, 'badge badge--danger');
    assert.equal(note.overdue, true);
  });

  test('bir gün gecikmə', () => {
    assert.equal(deadlineNote('2026-09-09', TODAY).label, '1 gün gecikib');
  });

  test('uzaq tarix sakit rəngdədir', () => {
    // Hər şeyi qırmızı etmək heç nəyi qırmızı etməməklə eynidir.
    assert.equal(deadlineNote('2026-09-30', TODAY).className, 'badge badge--neutral');
    assert.equal(deadlineNote('2026-09-12', TODAY).className, 'badge badge--warning');
  });

  test('ay/il sərhədini keçir', () => {
    assert.equal(deadlineNote('2026-10-01', '2026-09-30').label, 'Sabah son gün');
    assert.equal(deadlineNote('2027-01-01', '2026-12-31').label, 'Sabah son gün');
  });

  test('yararsız tarix sındırmır', () => {
    assert.equal(deadlineNote('', TODAY), null);
    assert.equal(deadlineNote('filan', TODAY), null);
    assert.equal(deadlineNote(null, TODAY), null);
  });
});

describe('təcililiyə görə sıralama', () => {
  const rows = [
    { title: 'uzaq', due_date: '2026-09-20', status: 'gözləyir' },
    { title: 'bitib', due_date: '2026-09-01', status: 'tamamlanıb' },
    { title: 'gecikib', due_date: '2026-09-05', status: 'gözləyir' },
    { title: 'yaxın', due_date: '2026-09-11', status: 'davam edir' },
  ];

  test('gecikmiş birinci, tamamlanmış sonuncu', () => {
    assert.deepEqual(
      sortByUrgency(rows, TODAY).map((r) => r.title),
      ['gecikib', 'yaxın', 'uzaq', 'bitib'],
    );
  });

  test('mənbə massivi dəyişdirilmir', () => {
    const before = rows.map((r) => r.title);
    sortByUrgency(rows, TODAY);
    assert.deepEqual(rows.map((r) => r.title), before);
  });

  test('tamamlanmışlar öz aralarında ən yenisi əvvəldədir', () => {
    const done = [
      { title: 'köhnə', due_date: '2026-08-01', status: 'tamamlanıb' },
      { title: 'yeni', due_date: '2026-09-01', status: 'tamamlanıb' },
    ];
    assert.deepEqual(sortByUrgency(done, TODAY).map((r) => r.title), ['yeni', 'köhnə']);
  });

  test('tarixsiz sətir siyahıdan İTMİR', () => {
    const mixed = [{ title: 'tarixsiz', due_date: null, status: 'gözləyir' }, ...rows];
    assert.equal(sortByUrgency(mixed, TODAY).length, 5);
  });

  test('boş siyahı', () => {
    assert.deepEqual(sortByUrgency([], TODAY), []);
    assert.deepEqual(sortByUrgency(undefined, TODAY), []);
  });
});
