import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:masterai/src/data/api_exception.dart';
import 'package:masterai/src/data/quiz_client.dart';

void main() {
  group('startQuiz', () {
    test('uğurlu başlama sessiya qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/chats/5/quiz/start');
        final body = jsonDecode(req.body) as Map<String, dynamic>;
        expect(body['material_id'], 3);
        return http.Response(
          jsonEncode({
            'chat_id': 5,
            'material_id': 3,
            'question_ids': [1, 2],
            'current_index': 0,
            'status': 'active',
          }),
          201,
        );
      });
      final client = QuizClient(baseUrl: 'https://x', httpClient: mock);
      final session = await client.startQuiz('tok', 5, materialId: 3);
      expect(session.status, 'active');
      expect(session.questionIds, [1, 2]);
    });

    test('409 → "artıq aktiv quiz var" mesajı', () async {
      final mock = MockClient((req) async => http.Response('{}', 409));
      final client = QuizClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.startQuiz('tok', 5, materialId: 3),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('aktiv quiz'))),
      );
    });

    test('403 → "yalnız materialı yükləyən" mesajı', () async {
      final mock = MockClient((req) async => http.Response('{}', 403));
      final client = QuizClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.startQuiz('tok', 5, materialId: 3),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('yükləyən'))),
      );
    });
  });
}
