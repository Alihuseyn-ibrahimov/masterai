class LiveSessionInfo {
  final int id;
  final int questionSetId;
  final String pin;
  final String status; // "waiting" | "active" | "finished"
  final int currentQuestionIndex;
  final String createdAt;

  const LiveSessionInfo({
    required this.id,
    required this.questionSetId,
    required this.pin,
    required this.status,
    required this.currentQuestionIndex,
    required this.createdAt,
  });

  factory LiveSessionInfo.fromJson(Map<String, dynamic> json) => LiveSessionInfo(
        id: json['id'] as int,
        questionSetId: json['question_set_id'] as int,
        pin: json['pin'] as String,
        status: json['status'] as String,
        currentQuestionIndex: json['current_question_index'] as int,
        createdAt: json['created_at'] as String,
      );
}

class LiveRankingRow {
  final int rank;
  final int participantId;
  final String displayName;
  final int score;

  const LiveRankingRow({
    required this.rank,
    required this.participantId,
    required this.displayName,
    required this.score,
  });

  factory LiveRankingRow.fromJson(Map<String, dynamic> json) => LiveRankingRow(
        rank: json['rank'] as int,
        participantId: json['participant_id'] as int,
        displayName: json['display_name'] as String,
        score: json['score'] as int,
      );
}

class LiveQuestionReport {
  final int index;
  final String question;
  final int correctIndex;
  final int correctCount;
  final int totalAnswers;
  final int? mostCommonWrongIndex;

  const LiveQuestionReport({
    required this.index,
    required this.question,
    required this.correctIndex,
    required this.correctCount,
    required this.totalAnswers,
    required this.mostCommonWrongIndex,
  });

  factory LiveQuestionReport.fromJson(Map<String, dynamic> json) => LiveQuestionReport(
        index: json['index'] as int,
        question: json['question'] as String,
        correctIndex: json['correct_index'] as int,
        correctCount: json['correct_count'] as int,
        totalAnswers: json['total_answers'] as int,
        mostCommonWrongIndex: json['most_common_wrong_index'] as int?,
      );
}

class LiveSessionReport {
  final int sessionId;
  final int totalQuestions;
  final List<LiveRankingRow> rankings;
  final List<LiveQuestionReport> perQuestion;

  const LiveSessionReport({
    required this.sessionId,
    required this.totalQuestions,
    required this.rankings,
    required this.perQuestion,
  });

  factory LiveSessionReport.fromJson(Map<String, dynamic> json) => LiveSessionReport(
        sessionId: json['session_id'] as int,
        totalQuestions: json['total_questions'] as int,
        rankings: (json['rankings'] as List)
            .cast<Map<String, dynamic>>()
            .map(LiveRankingRow.fromJson)
            .toList(),
        perQuestion: (json['per_question'] as List)
            .cast<Map<String, dynamic>>()
            .map(LiveQuestionReport.fromJson)
            .toList(),
      );
}
