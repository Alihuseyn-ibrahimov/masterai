import { test } from 'node:test';
import assert from 'node:assert/strict';

import { hasTopicStats, topicLine } from '../assets/js/topics.js';

test('hasTopicStats false when both lists empty or missing', () => {
  assert.equal(hasTopicStats({ strong: [], weak: [] }), false);
  assert.equal(hasTopicStats({}), false);
  assert.equal(hasTopicStats(null), false);
});

test('hasTopicStats true when either list has an entry', () => {
  assert.equal(hasTopicStats({ strong: [{ topic: 'a' }], weak: [] }), true);
  assert.equal(hasTopicStats({ strong: [], weak: [{ topic: 'a' }] }), true);
});

test('topicLine formats percent and answer count', () => {
  assert.equal(topicLine({ percent: 65, total: 3, correct: 2, topic: 'x' }), '65% düzgün (3 cavab)');
});
