import 'question_set.dart';

/// `GET /history/me` / `GET /history/student/{id}` sətri — canlı sessiya
/// VƏ ev tapşırığı nəticələri eyni siyahıda, xronoloji sıralanmış gəlir
/// (bax `server/app.py`, `_history_entries_for_student`).
class HistoryEntry {
  final String kind; // "live" | "homework"
  final String subject;
  final String title;
  final int score;
  final int totalQuestions;
  final String date;
  final int? chatId;
  final int? sessionId;

  const HistoryEntry({
    required this.kind,
    required this.subject,
    required this.title,
    required this.score,
    required this.totalQuestions,
    required this.date,
    required this.chatId,
    required this.sessionId,
  });

  String get subjectLabel => kSubjectLabels[subject] ?? subject;

  factory HistoryEntry.fromJson(Map<String, dynamic> json) => HistoryEntry(
        kind: json['kind'] as String,
        subject: json['subject'] as String,
        title: json['title'] as String,
        score: json['score'] as int,
        totalQuestions: json['total_questions'] as int,
        date: json['date'] as String,
        chatId: json['chat_id'] as int?,
        sessionId: json['session_id'] as int?,
      );
}
