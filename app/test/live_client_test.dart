import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:masterai/src/data/api_exception.dart';
import 'package:masterai/src/data/live_client.dart';

// Bax `masterai/CLAUDE.md`, "Dərs: Flutter app..." — `http.Response`-un
// kodlaşdırması `content-type` header-indən törəyir, Azərbaycan hərfləri
// olan fixture-larda bu HƏMİŞƏ açıq göstərilməlidir.
const _jsonHeaders = {'content-type': 'application/json'};

void main() {
  group('createQuestionSet', () {
    test('uğurlu yaradılma sual bankı qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/live/question-sets');
        final body = Uri.splitQueryString(req.body);
        expect(body['subject'], 'mentiq');
        expect(body['title'], 'Silloqizmlər');
        expect(body['kind'], 'link');
        expect(body['location'], 'https://x.az');
        return http.Response(
          jsonEncode({
            'id': 1,
            'subject': 'mentiq',
            'title': 'Silloqizmlər',
            'status': 'processing',
            'material_kind': 'link',
            'material_location': 'https://x.az',
            'error': null,
            'question_count': 0,
            'created_by': 1,
            'created_at': '2026-09-07T00:00:00Z',
          }),
          202,
          headers: _jsonHeaders,
        );
      });
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      final qs = await client.createQuestionSet(
        'tok',
        subject: 'mentiq',
        title: 'Silloqizmlər',
        location: 'https://x.az',
      );
      expect(qs.status, 'processing');
      expect(qs.subjectLabel, 'Məntiq');
    });

    test('400 → aydın xəta mesajı', () async {
      final mock = MockClient((req) async => http.Response('{}', 400));
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.createQuestionSet('tok', subject: 'mentiq', title: 'A', location: 'https://x.az'),
        throwsA(isA<ApiException>().having((e) => e.statusCode, 'statusCode', 400)),
      );
    });

    test('questionCount "question_count" sahəsi kimi göndərilir', () async {
      final mock = MockClient((req) async {
        final body = Uri.splitQueryString(req.body);
        expect(body['question_count'], '15');
        return http.Response(
          jsonEncode({
            'id': 1,
            'subject': 'mentiq',
            'title': 'A',
            'status': 'processing',
            'material_kind': 'link',
            'material_location': 'https://x.az',
            'error': null,
            'question_count': 0,
            'created_by': 1,
            'created_at': '2026-09-07T00:00:00Z',
          }),
          202,
          headers: _jsonHeaders,
        );
      });
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      await client.createQuestionSet(
        'tok', subject: 'mentiq', title: 'A', location: 'https://x.az', questionCount: 15,
      );
    });
  });

  group('listQuestionSets', () {
    test('siyahını parse edir', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/live/question-sets');
        return http.Response(
          jsonEncode([
            {
              'id': 1,
              'subject': 'informatika',
              'title': 'Alqoritmlər',
              'status': 'ready',
              'material_kind': 'link',
              'material_location': 'https://x.az',
              'error': null,
              'question_count': 5,
              'created_by': 1,
              'created_at': '2026-09-07T00:00:00Z',
            },
          ]),
          200,
          headers: _jsonHeaders,
        );
      });
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      final list = await client.listQuestionSets('tok');
      expect(list, hasLength(1));
      expect(list.first.questionCount, 5);
    });
  });

  group('createLiveSession', () {
    test('uğurlu yaradılma PIN-li sessiya qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/live/sessions');
        final body = jsonDecode(req.body) as Map<String, dynamic>;
        expect(body['question_set_id'], 7);
        return http.Response(
          jsonEncode({
            'id': 3,
            'question_set_id': 7,
            'pin': '123456',
            'status': 'waiting',
            'current_question_index': 0,
            'created_at': '2026-09-07T00:00:00Z',
          }),
          201,
          headers: _jsonHeaders,
        );
      });
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      final session = await client.createLiveSession('tok', 7);
      expect(session.pin, '123456');
      expect(session.status, 'waiting');
    });

    test('400 → "hələ hazır deyil" mesajı', () async {
      final mock = MockClient((req) async => http.Response('{}', 400));
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.createLiveSession('tok', 7),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('hazır deyil'))),
      );
    });
  });

  group('getReport', () {
    test('hesabatı parse edir', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/live/sessions/3/report');
        return http.Response(
          jsonEncode({
            'session_id': 3,
            'total_questions': 2,
            'rankings': [
              {'rank': 1, 'participant_id': 1, 'display_name': 'Əli', 'score': 2},
            ],
            'per_question': [
              {
                'index': 0,
                'question': 'Sual 1?',
                'correct_index': 0,
                'correct_count': 1,
                'total_answers': 2,
                'most_common_wrong_index': 2,
              },
            ],
          }),
          200,
          headers: _jsonHeaders,
        );
      });
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      final report = await client.getReport('tok', 3);
      expect(report.rankings.single.displayName, 'Əli');
      expect(report.perQuestion.single.mostCommonWrongIndex, 2);
    });
  });

  Map<String, dynamic> questionJson({String question = 'Köhnə sual?'}) => {
        'id': 5,
        'question_set_id': 1,
        'question': question,
        'options': ['A', 'B', 'C', 'D', 'E'],
        'correct_index': 0,
        'explanation': 'izah',
        'created_at': '2026-09-07T00:00:00Z',
      };

  group('listQuestions', () {
    test('sual siyahısını qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/live/question-sets/1/questions');
        return http.Response(jsonEncode([questionJson()]), 200, headers: _jsonHeaders);
      });
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      final questions = await client.listQuestions('tok', 1);
      expect(questions, hasLength(1));
      expect(questions[0].correctIndex, 0);
    });

    test('403 → ApiException', () async {
      final mock = MockClient((req) async => http.Response('{}', 403));
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(client.listQuestions('tok', 1), throwsA(isA<ApiException>()));
    });
  });

  group('updateQuestion', () {
    test('yenilənmiş sualı qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.method, 'PATCH');
        expect(req.url.path, '/live/questions/5');
        final body = jsonDecode(req.body) as Map<String, dynamic>;
        expect(body['question'], 'Yeni sual?');
        expect(body['correct_index'], 2);
        return http.Response(jsonEncode(questionJson(question: 'Yeni sual?')), 200, headers: _jsonHeaders);
      });
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      final updated = await client.updateQuestion(
        'tok', 5,
        question: 'Yeni sual?',
        options: ['A', 'B', 'C', 'D', 'E'],
        correctIndex: 2,
        explanation: 'izah',
      );
      expect(updated.question, 'Yeni sual?');
    });

    test('422 → ApiException', () async {
      final mock = MockClient((req) async => http.Response('{}', 422));
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.updateQuestion(
          'tok', 5,
          question: 'X',
          options: ['A', 'B'],
          correctIndex: 0,
          explanation: 'izah',
        ),
        throwsA(isA<ApiException>()),
      );
    });
  });

  group('deleteQuestion', () {
    test('204 → uğurla bitir', () async {
      final mock = MockClient((req) async {
        expect(req.method, 'DELETE');
        expect(req.url.path, '/live/questions/5');
        return http.Response('', 204);
      });
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      await client.deleteQuestion('tok', 5);
    });

    test('404 → ApiException', () async {
      final mock = MockClient((req) async => http.Response('{}', 404));
      final client = LiveClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(client.deleteQuestion('tok', 5), throwsA(isA<ApiException>()));
    });
  });
}
