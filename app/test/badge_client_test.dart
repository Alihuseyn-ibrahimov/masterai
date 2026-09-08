import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:masterai/src/data/api_exception.dart';
import 'package:masterai/src/data/badge_client.dart';

const _jsonHeaders = {'content-type': 'application/json'};

void main() {
  group('getMyBadges', () {
    test('nişan siyahısını qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/badges/me');
        expect(req.headers['Authorization'], 'Bearer tok');
        return http.Response(
          jsonEncode([
            {'badge_type': 'ilk_addim', 'earned': true, 'earned_at': '2026-09-08T00:00:00Z'},
            {'badge_type': 'yuz_faiz', 'earned': false, 'earned_at': null},
          ]),
          200,
          headers: _jsonHeaders,
        );
      });
      final client = BadgeClient(baseUrl: 'https://x', httpClient: mock);
      final badges = await client.getMyBadges('tok');
      expect(badges, hasLength(2));
      expect(badges[0].earned, true);
      expect(badges[1].earned, false);
      expect(badges[1].earnedAt, isNull);
    });

    test('şəbəkə xətası ApiException atır', () async {
      final mock = MockClient((req) async => throw Exception('boom'));
      final client = BadgeClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(client.getMyBadges('tok'), throwsA(isA<ApiException>()));
    });

    test('401 → ApiException', () async {
      final mock = MockClient((req) async => http.Response('{}', 401));
      final client = BadgeClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(client.getMyBadges('tok'), throwsA(isA<ApiException>()));
    });
  });
}
