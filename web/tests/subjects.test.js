import { test, describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
  SUBJECTS,
  homeworkProgressBadge,
  statusBadge,
  subjectColorVar,
  subjectLabel,
} from '../assets/js/subjects.js';

describe('fənn kataloqu', () => {
  test('backend-dəki altı fənn var', () => {
    assert.deepEqual(
      SUBJECTS.map((s) => s.key),
      ['mentiq', 'informatika', 'dunyagorusu', 'azerbaycan_dili', 'qanunvericilik', 'xarici_dil'],
    );
  });

  test('etiket qaytarır', () => {
    assert.equal(subjectLabel('qanunvericilik'), 'Qanunvericilik');
  });

  test('naməlum açarda sındırmır', () => {
    assert.equal(subjectLabel('yoxdur'), 'yoxdur');
    // Ehtiyat dəyəri adi defisdir: em-dash bütün layihədə qadağandır
    // (bax tests/test_web_pages.py::TestTypographicDiscipline).
    assert.equal(subjectLabel(null), '-');
  });

  test('rəng dəyişəni CSS formatındadır', () => {
    assert.equal(subjectColorVar('mentiq'), 'var(--subject-mentiq)');
  });

  test('naməlum fənn rəngsiz qalmır', () => {
    assert.equal(subjectColorVar('yoxdur'), 'var(--color-primary)');
  });
});

describe('statusBadge', () => {
  test('üç statusu fərqləndirir', () => {
    assert.match(statusBadge('ready').className, /success/);
    assert.match(statusBadge('failed').className, /danger/);
    assert.match(statusBadge('processing').className, /warning/);
  });

  test('naməlum status "hazırlanır" sayılır (təhlükəsiz defolt)', () => {
    // Naməlum statusu "hazırdır" saymaq müəllimi yarımçıq bankla
    // sessiya başlatmağa aparardı.
    assert.match(statusBadge('nese').className, /warning/);
    assert.match(statusBadge(undefined).className, /warning/);
  });
});

describe('homeworkProgressBadge', () => {
  it('hamı tamamlayıbsa uğur rəngi', () => {
    assert.match(homeworkProgressBadge(9, 9).className, /success/);
  });

  it('heç kim başlamayıbsa neytral', () => {
    assert.match(homeworkProgressBadge(0, 18).className, /neutral/);
  });

  it('qismən tamamlanıbsa məlumat rəngi', () => {
    assert.match(homeworkProgressBadge(6, 18).className, /info/);
  });

  it('üzv yoxdursa sıfıra bölmə olmur', () => {
    const badge = homeworkProgressBadge(0, 0);
    assert.ok(badge.label.length > 0);
  });
});
