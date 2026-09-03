import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:masterai/src/models/chat_item.dart';

void main() {
  group('fromHistoryRow', () {
    test('kind=text → TextChatItem', () {
      final item = ChatItem.fromHistoryRow({
        'id': 1,
        'chat_id': 5,
        'sender_id': 2,
        'kind': 'text',
        'content': 'Salam',
        'created_at': '2026-09-03T00:00:00Z',
      });
      expect(item, isA<TextChatItem>());
      final t = item as TextChatItem;
      expect(t.senderId, 2);
      expect(t.content, 'Salam');
    });

    test('kind=quiz_question → content JSON kimi açılır', () {
      final content = jsonEncode({
        'question_id': 10,
        'question': 'Paytaxt hansıdır?',
        'options': ['Bakı', 'Gəncə', 'Sumqayıt', 'Şəki', 'Naxçıvan'],
      });
      final item = ChatItem.fromHistoryRow({
        'id': 2,
        'kind': 'quiz_question',
        'content': content,
        'created_at': '2026-09-03T00:00:00Z',
      });
      expect(item, isA<QuizQuestionItem>());
      final q = item as QuizQuestionItem;
      expect(q.questionId, 10);
      expect(q.options, hasLength(5));
    });

    test('kind=quiz_result → correct_index/explanation/answers açılır', () {
      final content = jsonEncode({
        'question_id': 10,
        'correct_index': 0,
        'explanation': 'Bakı Azərbaycanın paytaxtıdır.',
        'answers': [
          {'user_id': 1, 'chosen_index': 0, 'is_correct': true},
        ],
      });
      final item = ChatItem.fromHistoryRow({
        'id': 3,
        'kind': 'quiz_result',
        'content': content,
        'created_at': '2026-09-03T00:00:00Z',
      });
      expect(item, isA<QuizResultItem>());
      final r = item as QuizResultItem;
      expect(r.correctIndex, 0);
      expect(r.answers.single.isCorrect, isTrue);
    });

    test('kind=system + JSON content (kind:quiz_finished) → QuizFinishedItem', () {
      final content = jsonEncode({
        'kind': 'quiz_finished',
        'total_questions': 2,
        'scores': {'1': 2, '2': 1},
      });
      final item = ChatItem.fromHistoryRow({
        'id': 4,
        'kind': 'system',
        'content': content,
        'created_at': '2026-09-03T00:00:00Z',
      });
      expect(item, isA<QuizFinishedItem>());
      final f = item as QuizFinishedItem;
      expect(f.totalQuestions, 2);
      expect(f.scores[1], 2);
      expect(f.scores[2], 1);
    });

    test('kind=system + adi mətn (material bildirişi) → SystemChatItem', () {
      final item = ChatItem.fromHistoryRow({
        'id': 5,
        'kind': 'system',
        'content': 'Material hazırdır! 3 sual yaradıldı.',
        'created_at': '2026-09-03T00:00:00Z',
      });
      expect(item, isA<SystemChatItem>());
      expect((item as SystemChatItem).content, contains('hazırdır'));
    });
  });

  group('fromLiveEvent', () {
    test('type=message, kind=text → TextChatItem', () {
      final item = ChatItem.fromLiveEvent({
        'type': 'message',
        'id': 1,
        'chat_id': 5,
        'sender_id': 3,
        'kind': 'text',
        'content': 'Necəsən?',
        'created_at': '2026-09-03T00:00:00Z',
      });
      expect(item, isA<TextChatItem>());
    });

    test('type=message, kind=system → SystemChatItem (adi mətn, JSON yox)', () {
      final item = ChatItem.fromLiveEvent({
        'type': 'message',
        'id': 2,
        'kind': 'system',
        'content': 'Material emalı uğursuz oldu: xəta',
        'created_at': '2026-09-03T00:00:00Z',
      });
      expect(item, isA<SystemChatItem>());
    });

    test('type=quiz_question → sahələr üst səviyyədən oxunur (nested JSON yox)', () {
      final item = ChatItem.fromLiveEvent({
        'type': 'quiz_question',
        'question_id': 7,
        'question': 'Sual?',
        'options': ['A', 'B', 'C', 'D', 'E'],
        'message_id': 9,
      });
      expect(item, isA<QuizQuestionItem>());
      expect((item as QuizQuestionItem).questionId, 7);
    });

    test('type=quiz_finished → scores string açarları int-ə çevrilir', () {
      final item = ChatItem.fromLiveEvent({
        'type': 'quiz_finished',
        'total_questions': 2,
        'scores': {'1': 2, '2': 1},
        'message_id': 11,
      });
      expect(item, isA<QuizFinishedItem>());
      expect((item as QuizFinishedItem).scores[1], 2);
    });

    test('type=history/error → null (chat_socket.dart ayrıca idarə edir)', () {
      expect(ChatItem.fromLiveEvent({'type': 'history', 'messages': []}), isNull);
      expect(ChatItem.fromLiveEvent({'type': 'error', 'detail': 'x'}), isNull);
    });
  });
}
