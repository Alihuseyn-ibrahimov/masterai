import 'question_set.dart' show kSubjectLabels;

class HomeworkAssignmentInfo {
  final int id;
  final int chatId;
  final int questionSetId;
  final String dueDate;
  final int createdBy;
  final String createdAt;
  final int completedCount;
  final int totalMembers;

  const HomeworkAssignmentInfo({
    required this.id,
    required this.chatId,
    required this.questionSetId,
    required this.dueDate,
    required this.createdBy,
    required this.createdAt,
    required this.completedCount,
    required this.totalMembers,
  });

  factory HomeworkAssignmentInfo.fromJson(Map<String, dynamic> json) => HomeworkAssignmentInfo(
        id: json['id'] as int,
        chatId: json['chat_id'] as int,
        questionSetId: json['question_set_id'] as int,
        dueDate: json['due_date'] as String,
        createdBy: json['created_by'] as int,
        createdAt: json['created_at'] as String,
        completedCount: json['completed_count'] as int,
        totalMembers: json['total_members'] as int,
      );
}

class HomeworkQuestionPayload {
  final int index;
  final int total;
  final String question;
  final List<String> options;

  const HomeworkQuestionPayload({
    required this.index,
    required this.total,
    required this.question,
    required this.options,
  });

  factory HomeworkQuestionPayload.fromJson(Map<String, dynamic> json) => HomeworkQuestionPayload(
        index: json['index'] as int,
        total: json['total'] as int,
        question: json['question'] as String,
        options: (json['options'] as List).cast<String>(),
      );
}

class HomeworkAttemptState {
  final int attemptId;
  final String status;
  final int currentQuestionIndex;
  final int score;
  final HomeworkQuestionPayload? question;

  const HomeworkAttemptState({
    required this.attemptId,
    required this.status,
    required this.currentQuestionIndex,
    required this.score,
    required this.question,
  });

  factory HomeworkAttemptState.fromJson(Map<String, dynamic> json) => HomeworkAttemptState(
        attemptId: json['attempt_id'] as int,
        status: json['status'] as String,
        currentQuestionIndex: json['current_question_index'] as int,
        score: json['score'] as int,
        question: json['question'] == null
            ? null
            : HomeworkQuestionPayload.fromJson(json['question'] as Map<String, dynamic>),
      );
}

class HomeworkAnswerResult {
  final bool isCorrect;
  final int correctIndex;
  final String explanation;
  final HomeworkQuestionPayload? nextQuestion;

  const HomeworkAnswerResult({
    required this.isCorrect,
    required this.correctIndex,
    required this.explanation,
    required this.nextQuestion,
  });

  factory HomeworkAnswerResult.fromJson(Map<String, dynamic> json) => HomeworkAnswerResult(
        isCorrect: json['is_correct'] as bool,
        correctIndex: json['correct_index'] as int,
        explanation: json['explanation'] as String,
        nextQuestion: json['next_question'] == null
            ? null
            : HomeworkQuestionPayload.fromJson(json['next_question'] as Map<String, dynamic>),
      );
}

class HomeworkReportRow {
  final int studentId;
  final String displayName;
  final String status; // "gözləyir" | "davam edir" | "tamamlanıb"
  final int? score;

  const HomeworkReportRow({
    required this.studentId,
    required this.displayName,
    required this.status,
    required this.score,
  });

  factory HomeworkReportRow.fromJson(Map<String, dynamic> json) => HomeworkReportRow(
        studentId: json['student_id'] as int,
        displayName: json['display_name'] as String,
        status: json['status'] as String,
        score: json['score'] as int?,
      );
}

class MyAssignmentInfo {
  final int assignmentId;
  final int chatId;
  final String subject;
  final String title;
  final String dueDate;
  final String status; // "gözləyir" | "davam edir" | "tamamlanıb"
  final int? score;

  const MyAssignmentInfo({
    required this.assignmentId,
    required this.chatId,
    required this.subject,
    required this.title,
    required this.dueDate,
    required this.status,
    required this.score,
  });

  String get subjectLabel => kSubjectLabels[subject] ?? subject;

  factory MyAssignmentInfo.fromJson(Map<String, dynamic> json) => MyAssignmentInfo(
        assignmentId: json['assignment_id'] as int,
        chatId: json['chat_id'] as int,
        subject: json['subject'] as String,
        title: json['title'] as String,
        dueDate: json['due_date'] as String,
        status: json['status'] as String,
        score: json['score'] as int?,
      );
}
