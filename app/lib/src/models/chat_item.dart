/// Çat lentindəki bir "sətir" — həm `history` massivindəki xam DB
/// sətirlərindən (`ChatItem.fromHistoryRow`), həm də canlı WebSocket
/// hadisələrindən (`ChatItem.fromLiveEvent`) yaranır.
///
/// VACİB asimmetriya (backend-in `message_store`+`quiz_runner` naxışından):
/// - `history`-dəki sətirlərdə `kind="quiz_question"/"quiz_result"` üçün
///   `content` HƏMİŞƏ JSON sətirdir (backend onu elə saxlayır).
/// - `kind="system"` isə İKİ formatı qarışdırır: material bildirişləri üçün
///   sadə mətn (`"Material hazırdır! ..."`), quiz bitmə xülasəsi üçün isə
///   JSON (`{"kind":"quiz_finished",...}`). Ona görə `fromHistoryRow`
///   `content`-i əvvəlcə JSON kimi açmağa CƏHD EDİR, uğursuz olsa sadə
///   mətn kimi göstərir.
/// - Canlı hadisələrdə bu qarışıqlıq YOXDUR — hər hadisə növünün öz
///   ayrıca `type`-ı var (`quiz_finished` də daxil olmaqla), sahələr
///   birbaşa üst səviyyədədir (JSON-daxili-JSON yoxdur).
library;

import 'dart:convert';

sealed class ChatItem {
  final int id;
  final String createdAt;

  const ChatItem({required this.id, required this.createdAt});

  static ChatItem fromHistoryRow(Map<String, dynamic> row) {
    final id = row['id'] as int;
    final createdAt = row['created_at'] as String;
    final kind = row['kind'] as String;
    final content = row['content'] as String;

    if (kind == 'text') {
      return TextChatItem(
        id: id,
        createdAt: createdAt,
        senderId: row['sender_id'] as int?,
        content: content,
      );
    }
    if (kind == 'quiz_question') {
      final payload = jsonDecode(content) as Map<String, dynamic>;
      return QuizQuestionItem(
        id: id,
        createdAt: createdAt,
        questionId: payload['question_id'] as int,
        question: payload['question'] as String,
        options: (payload['options'] as List).cast<String>(),
      );
    }
    if (kind == 'quiz_result') {
      final payload = jsonDecode(content) as Map<String, dynamic>;
      return QuizResultItem(
        id: id,
        createdAt: createdAt,
        questionId: payload['question_id'] as int,
        correctIndex: payload['correct_index'] as int,
        explanation: payload['explanation'] as String,
        answers: (payload['answers'] as List)
            .map((a) => QuizAnswer.fromJson(a as Map<String, dynamic>))
            .toList(),
      );
    }
    // kind == "system" — quiz_finished xülasəsi ola bilər (JSON) ya da
    // sadə material bildirişi (düz mətn).
    try {
      final decoded = jsonDecode(content);
      if (decoded is Map<String, dynamic> && decoded['kind'] == 'quiz_finished') {
        return QuizFinishedItem(
          id: id,
          createdAt: createdAt,
          totalQuestions: decoded['total_questions'] as int,
          scores: (decoded['scores'] as Map).map(
            (k, v) => MapEntry(int.parse(k as String), v as int),
          ),
        );
      }
    } catch (_) {
      // JSON deyil — aşağıda sadə mətn kimi göstərilir.
    }
    return SystemChatItem(id: id, createdAt: createdAt, content: content);
  }

  /// `null` qaytarır — `type: "history"`/`"error"` kimi bu funksiyaya aid
  /// olmayan hadisələr üçün (chat_socket.dart onları ayrıca idarə edir).
  static ChatItem? fromLiveEvent(Map<String, dynamic> event) {
    final type = event['type'] as String;
    switch (type) {
      case 'message':
        final kind = event['kind'] as String;
        final content = event['content'] as String;
        if (kind == 'system') {
          return SystemChatItem(
            id: event['id'] as int,
            createdAt: event['created_at'] as String,
            content: content,
          );
        }
        return TextChatItem(
          id: event['id'] as int,
          createdAt: event['created_at'] as String,
          senderId: event['sender_id'] as int?,
          content: content,
        );
      case 'quiz_question':
        return QuizQuestionItem(
          id: event['message_id'] as int,
          createdAt: DateTime.now().toIso8601String(),
          questionId: event['question_id'] as int,
          question: event['question'] as String,
          options: (event['options'] as List).cast<String>(),
        );
      case 'quiz_result':
        return QuizResultItem(
          id: event['message_id'] as int,
          createdAt: DateTime.now().toIso8601String(),
          questionId: event['question_id'] as int,
          correctIndex: event['correct_index'] as int,
          explanation: event['explanation'] as String,
          answers: (event['answers'] as List)
              .map((a) => QuizAnswer.fromJson(a as Map<String, dynamic>))
              .toList(),
        );
      case 'quiz_finished':
        return QuizFinishedItem(
          id: event['message_id'] as int,
          createdAt: DateTime.now().toIso8601String(),
          totalQuestions: event['total_questions'] as int,
          scores: (event['scores'] as Map).map(
            (k, v) => MapEntry(int.parse(k as String), v as int),
          ),
        );
      default:
        return null;
    }
  }
}

class TextChatItem extends ChatItem {
  final int? senderId;
  final String content;

  const TextChatItem({
    required super.id,
    required super.createdAt,
    required this.senderId,
    required this.content,
  });
}

class SystemChatItem extends ChatItem {
  final String content;

  const SystemChatItem({
    required super.id,
    required super.createdAt,
    required this.content,
  });
}

class QuizQuestionItem extends ChatItem {
  final int questionId;
  final String question;
  final List<String> options;

  const QuizQuestionItem({
    required super.id,
    required super.createdAt,
    required this.questionId,
    required this.question,
    required this.options,
  });
}

class QuizAnswer {
  final int userId;
  final int chosenIndex;
  final bool isCorrect;

  const QuizAnswer({
    required this.userId,
    required this.chosenIndex,
    required this.isCorrect,
  });

  factory QuizAnswer.fromJson(Map<String, dynamic> json) => QuizAnswer(
        userId: json['user_id'] as int,
        chosenIndex: json['chosen_index'] as int,
        isCorrect: json['is_correct'] as bool,
      );
}

class QuizResultItem extends ChatItem {
  final int questionId;
  final int correctIndex;
  final String explanation;
  final List<QuizAnswer> answers;

  const QuizResultItem({
    required super.id,
    required super.createdAt,
    required this.questionId,
    required this.correctIndex,
    required this.explanation,
    required this.answers,
  });
}

class QuizFinishedItem extends ChatItem {
  final int totalQuestions;
  final Map<int, int> scores;

  const QuizFinishedItem({
    required super.id,
    required super.createdAt,
    required this.totalQuestions,
    required this.scores,
  });
}
