import { test } from 'node:test';
import assert from 'node:assert/strict';

import { azn, debtLabel, monthLabel, percent, trendShare } from '../assets/js/kassa.js';

test('azn groups thousands and keeps the sign', () => {
  assert.equal(azn(0), '0 AZN');
  assert.equal(azn(1234), '1 234 AZN');
  assert.equal(azn(-450), '-450 AZN');
  assert.equal(azn(1200000), '1 200 000 AZN');
});

test('percent shows a dash when nothing is expected', () => {
  assert.equal(percent(null), '-');
  assert.equal(percent(0.8333), '83%');
  assert.equal(percent(1), '100%');
});

test('monthLabel uses short Azerbaijani month names', () => {
  assert.equal(monthLabel('2026-11'), 'Noy 2026');
  assert.equal(monthLabel('2027-01'), 'Yan 2027');
  assert.equal(monthLabel('bad'), 'bad');
});

test('debtLabel mentions streak and last payment', () => {
  assert.equal(debtLabel({ days_overdue: 5, unpaid_months: 1, last_paid_month: '2026-10' }),
    '5 gün gecikir · son ödəniş: Okt 2026');
  assert.equal(debtLabel({ days_overdue: 19, unpaid_months: 3, last_paid_month: null }),
    '19 gün gecikir · 3 aydır ödəmir · heç ödəməyib');
});

test('trendShare is clamped and safe for zero', () => {
  assert.equal(trendShare(50, 0), 0);
  assert.equal(trendShare(50, 100), 0.5);
  assert.equal(trendShare(150, 100), 1);
});
