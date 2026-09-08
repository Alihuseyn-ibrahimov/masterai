import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:masterai/src/models/question_set.dart';
import 'package:masterai/src/theme/app_subject_colors.dart';

void main() {
  group('AppSubjectColors.forSubject', () {
    test('kSubjectLabels-in bütün açarları üçün rəng qaytarır (light)', () {
      for (final key in kSubjectLabels.keys) {
        expect(AppSubjectColors.light.forSubject(key), isNotNull, reason: 'açar: $key');
      }
    });

    test('kSubjectLabels-in bütün açarları üçün rəng qaytarır (dark)', () {
      for (final key in kSubjectLabels.keys) {
        expect(AppSubjectColors.dark.forSubject(key), isNotNull, reason: 'açar: $key');
      }
    });

    test('naməlum açar üçün null qaytarır', () {
      expect(AppSubjectColors.light.forSubject('riyaziyyat'), isNull);
    });

    test('light və dark eyni fənn üçün fərqli rəng verir', () {
      expect(AppSubjectColors.light.mentiq, isNot(AppSubjectColors.dark.mentiq));
    });
  });

  group('copyWith/lerp', () {
    test('copyWith yalnız verilən sahəni dəyişir', () {
      final updated = AppSubjectColors.light.copyWith(mentiq: const Color(0xFF000000));
      expect(updated.mentiq, const Color(0xFF000000));
      expect(updated.informatika, AppSubjectColors.light.informatika);
    });

    test('lerp t=0-da özünü qaytarır', () {
      final result = AppSubjectColors.light.lerp(AppSubjectColors.dark, 0);
      expect(result.mentiq, AppSubjectColors.light.mentiq);
    });
  });
}
