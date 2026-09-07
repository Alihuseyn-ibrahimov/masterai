/// Sual bankının BİR sualının TAM (düzgün cavab+izah daxil) məlumatı —
/// yalnız müəllim redaktə ekranı üçün (bax Sual redaktə/təsdiq ekranı,
/// Faza 5). Tələbəyə göstərilən sual formatından (`options`-yalnız)
/// fərqli olaraq bura düzgün cavab da daxildir.
class LiveQuestionInfo {
  final int id;
  final int questionSetId;
  final String question;
  final List<String> options;
  final int correctIndex;
  final String explanation;
  final String createdAt;

  const LiveQuestionInfo({
    required this.id,
    required this.questionSetId,
    required this.question,
    required this.options,
    required this.correctIndex,
    required this.explanation,
    required this.createdAt,
  });

  factory LiveQuestionInfo.fromJson(Map<String, dynamic> json) => LiveQuestionInfo(
        id: json['id'] as int,
        questionSetId: json['question_set_id'] as int,
        question: json['question'] as String,
        options: (json['options'] as List).cast<String>(),
        correctIndex: json['correct_index'] as int,
        explanation: json['explanation'] as String,
        createdAt: json['created_at'] as String,
      );
}
