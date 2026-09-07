import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:masterai/src/data/api_exception.dart';
import 'package:masterai/src/data/history_client.dart';

const _jsonHeaders = {'content-type': 'application/json'};

const _entryJson = {
  'kind': 'homework',
  'subject': 'mentiq',
  'title': 'Silloqizmlər',
  'score': 2,
  'total_questions': 3,
  'date': '2026-09-07T00:00:00Z',
  'chat_id': 5,
  'session_id': null,
};

void main() {
  group('getMyHistory', () {
    test('uğurlu sorğu HistoryEntry siyahısı qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/history/me');
        expect(req.headers['Authorization'], 'Bearer tok');
        return http.Response(jsonEncode([_entryJson]), 200, headers: _jsonHeaders);
      });
      final client = HistoryClient(baseUrl: 'https://x', httpClient: mock);
      final entries = await client.getMyHistory('tok');
      expect(entries, hasLength(1));
      expect(entries[0].kind, 'homework');
      expect(entries[0].score, 2);
      expect(entries[0].chatId, 5);
      expect(entries[0].sessionId, isNull);
    });

    test('şəbəkə xətası ApiException atır', () async {
      final mock = MockClient((req) async => throw Exception('boom'));
      final client = HistoryClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(client.getMyHistory('tok'), throwsA(isA<ApiException>()));
    });
  });

  group('getStudentHistory', () {
    test('düzgün ID ilə çağırır', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/history/student/42');
        return http.Response(jsonEncode([_entryJson]), 200, headers: _jsonHeaders);
      });
      final client = HistoryClient(baseUrl: 'https://x', httpClient: mock);
      final entries = await client.getStudentHistory('tok', 42);
      expect(entries, hasLength(1));
    });

    test('403 → icazə mesajı', () async {
      final mock = MockClient((req) async => http.Response('{}', 403));
      final client = HistoryClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.getStudentHistory('tok', 42),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('icazə'))),
      );
    });
  });
}
