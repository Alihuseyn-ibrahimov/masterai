import 'package:flutter_test/flutter_test.dart';
import 'package:masterai/src/models/badge.dart';

const _allBadgeTypes = ['ilk_addim', 'yuz_faiz', 'fenn_ustasi', 'suretli_eqli', 'silsile_5'];

void main() {
  group('BadgeInfo.meta', () {
    test('bütün bilinən badge_type-lar üçün metadata var', () {
      for (final type in _allBadgeTypes) {
        final badge = BadgeInfo(badgeType: type, earned: true, earnedAt: '2026-09-08');
        expect(badge.meta.title, isNotEmpty, reason: 'açar: $type');
        expect(badge.meta.emoji, isNotEmpty, reason: 'açar: $type');
      }
    });

    test('naməlum badge_type üçün geri dönüş metadatası verir', () {
      final badge = BadgeInfo(badgeType: 'naməlum_tip', earned: false, earnedAt: null);
      expect(badge.meta.title, 'naməlum_tip');
    });
  });

  group('BadgeInfo.fromJson', () {
    test('sahələri düzgün parse edir', () {
      final badge = BadgeInfo.fromJson({
        'badge_type': 'ilk_addim',
        'earned': true,
        'earned_at': '2026-09-08T00:00:00Z',
      });
      expect(badge.badgeType, 'ilk_addim');
      expect(badge.earned, true);
      expect(badge.earnedAt, '2026-09-08T00:00:00Z');
    });
  });
}
