import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:masterai/src/data/api_exception.dart';
import 'package:masterai/src/data/homework_client.dart';

// Bax `masterai/CLAUDE.md`, "Dərs: Flutter app..." — `http.Response`-un
// kodlaşdırması `content-type` header-indən törəyir, Azərbaycan hərfləri
// olan fixture-larda bu HƏMİŞƏ açıq göstərilməlidir.
const _jsonHeaders = {'content-type': 'application/json'};

void main() {
  group('createAssignment', () {
    test('uğurlu yaradılma tapşırıq qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/homework/assignments');
        final body = jsonDecode(req.body) as Map<String, dynamic>;
        expect(body['chat_id'], 5);
        expect(body['question_set_id'], 7);
        expect(body['due_date'], '2026-09-14');
        return http.Response(
          jsonEncode({
            'id': 1,
            'chat_id': 5,
            'question_set_id': 7,
            'due_date': '2026-09-14',
            'created_by': 1,
            'created_at': '2026-09-07T00:00:00Z',
            'completed_count': 0,
            'total_members': 3,
          }),
          201,
          headers: _jsonHeaders,
        );
      });
      final client = HomeworkClient(baseUrl: 'https://x', httpClient: mock);
      final a = await client.createAssignment('tok', chatId: 5, questionSetId: 7, dueDate: '2026-09-14');
      expect(a.totalMembers, 3);
    });

    test('400 → "hazır deyil" mesajı', () async {
      final mock = MockClient((req) async => http.Response('{}', 400));
      final client = HomeworkClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.createAssignment('tok', chatId: 5, questionSetId: 7, dueDate: '2026-09-14'),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('hazır deyil'))),
      );
    });
  });

  group('listAssignments', () {
    test('siyahını parse edir', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/homework/assignments');
        expect(req.url.queryParameters['chat_id'], '5');
        return http.Response(
          jsonEncode([
            {
              'id': 1, 'chat_id': 5, 'question_set_id': 7, 'due_date': '2026-09-14',
              'created_by': 1, 'created_at': '2026-09-07T00:00:00Z',
              'completed_count': 1, 'total_members': 3,
            },
          ]),
          200,
          headers: _jsonHeaders,
        );
      });
      final client = HomeworkClient(baseUrl: 'https://x', httpClient: mock);
      final list = await client.listAssignments('tok', chatId: 5);
      expect(list, hasLength(1));
      expect(list.first.completedCount, 1);
    });
  });

  group('getReport', () {
    test('hesabat sətirlərini parse edir', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/homework/assignments/1/report');
        return http.Response(
          jsonEncode([
            {'student_id': 2, 'display_name': 'Əli', 'status': 'tamamlanıb', 'score': 3},
            {'student_id': 3, 'display_name': 'Vəli', 'status': 'gözləyir', 'score': null},
          ]),
          200,
          headers: _jsonHeaders,
        );
      });
      final client = HomeworkClient(baseUrl: 'https://x', httpClient: mock);
      final rows = await client.getReport('tok', 1);
      expect(rows, hasLength(2));
      expect(rows.first.displayName, 'Əli');
      expect(rows.last.score, isNull);
    });
  });

  group('listMyAssignments', () {
    test('tapşırıqları parse edir', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/homework/my-assignments');
        return http.Response(
          jsonEncode([
            {
              'assignment_id': 1, 'chat_id': 5, 'subject': 'mentiq', 'title': 'Silloqizmlər',
              'due_date': '2026-09-14', 'status': 'gözləyir', 'score': null,
            },
          ]),
          200,
          headers: _jsonHeaders,
        );
      });
      final client = HomeworkClient(baseUrl: 'https://x', httpClient: mock);
      final list = await client.listMyAssignments('tok');
      expect(list.single.subject, 'mentiq');
    });
  });

  group('startAttempt', () {
    test('cəhd vəziyyətini parse edir (sual daxil)', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/homework/assignments/1/start');
        return http.Response(
          jsonEncode({
            'attempt_id': 9, 'status': 'in_progress', 'current_question_index': 0, 'score': 0,
            'question': {'index': 0, 'total': 2, 'question': 'Sual 1?', 'options': ['A', 'B']},
          }),
          200,
          headers: _jsonHeaders,
        );
      });
      final client = HomeworkClient(baseUrl: 'https://x', httpClient: mock);
      final state = await client.startAttempt('tok', 1);
      expect(state.attemptId, 9);
      expect(state.question!.question, 'Sual 1?');
    });
  });

  group('answer', () {
    test('nəticəni parse edir (sonuncu sual — next_question yoxdur)', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/homework/attempts/9/answer');
        final body = jsonDecode(req.body) as Map<String, dynamic>;
        expect(body['question_index'], 0);
        expect(body['chosen_index'], 1);
        return http.Response(
          jsonEncode({
            'is_correct': true, 'correct_index': 1, 'explanation': 'izah', 'next_question': null,
          }),
          200,
          headers: _jsonHeaders,
        );
      });
      final client = HomeworkClient(baseUrl: 'https://x', httpClient: mock);
      final result = await client.answer('tok', attemptId: 9, questionIndex: 0, chosenIndex: 1);
      expect(result.isCorrect, true);
      expect(result.nextQuestion, isNull);
    });
  });
}
