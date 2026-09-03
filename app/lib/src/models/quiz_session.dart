class QuizSessionInfo {
  final int chatId;
  final int materialId;
  final List<int> questionIds;
  final int currentIndex;
  final String status; // "active" | "finished"

  const QuizSessionInfo({
    required this.chatId,
    required this.materialId,
    required this.questionIds,
    required this.currentIndex,
    required this.status,
  });

  factory QuizSessionInfo.fromJson(Map<String, dynamic> json) => QuizSessionInfo(
        chatId: json['chat_id'] as int,
        materialId: json['material_id'] as int,
        questionIds: (json['question_ids'] as List).cast<int>(),
        currentIndex: json['current_index'] as int,
        status: json['status'] as String,
      );
}
