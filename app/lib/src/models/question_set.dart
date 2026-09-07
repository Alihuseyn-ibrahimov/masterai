/// `server/question_set_store.py`-dəki `SUBJECTS`-in Dart tərəfi — kod
/// backend-lə eyni sırada saxlanılıb ki, UI-dakı fənn seçimi ilə API
/// dəyəri uyğun qalsın.
const Map<String, String> kSubjectLabels = {
  'mentiq': 'Məntiq',
  'informatika': 'İnformatika',
  'dunyagorusu': 'Dünyagörüşü',
  'azerbaycan_dili': 'Azərbaycan dili',
  'qanunvericilik': 'Qanunvericilik',
  'xarici_dil': 'Xarici dil',
};

class QuestionSetInfo {
  final int id;
  final String subject;
  final String title;
  final String status; // "processing" | "ready" | "failed"
  final String materialKind; // "link" | "pdf" | "image"
  final String materialLocation;
  final String? error;
  final int questionCount;
  final int createdBy;
  final String createdAt;

  const QuestionSetInfo({
    required this.id,
    required this.subject,
    required this.title,
    required this.status,
    required this.materialKind,
    required this.materialLocation,
    required this.error,
    required this.questionCount,
    required this.createdBy,
    required this.createdAt,
  });

  String get subjectLabel => kSubjectLabels[subject] ?? subject;

  factory QuestionSetInfo.fromJson(Map<String, dynamic> json) => QuestionSetInfo(
        id: json['id'] as int,
        subject: json['subject'] as String,
        title: json['title'] as String,
        status: json['status'] as String,
        materialKind: json['material_kind'] as String,
        materialLocation: json['material_location'] as String,
        error: json['error'] as String?,
        questionCount: json['question_count'] as int,
        createdBy: json['created_by'] as int,
        createdAt: json['created_at'] as String,
      );
}
