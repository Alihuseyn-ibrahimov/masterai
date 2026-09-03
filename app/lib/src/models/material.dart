class MaterialInfo {
  final int id;
  final int chatId;
  final int uploadedBy;
  final String kind; // "link" | "pdf" | "image"
  final String location;
  final String? label;
  final String status; // "processing" | "ready" | "failed"
  final String createdAt;

  const MaterialInfo({
    required this.id,
    required this.chatId,
    required this.uploadedBy,
    required this.kind,
    required this.location,
    required this.label,
    required this.status,
    required this.createdAt,
  });

  factory MaterialInfo.fromJson(Map<String, dynamic> json) => MaterialInfo(
        id: json['id'] as int,
        chatId: json['chat_id'] as int,
        uploadedBy: json['uploaded_by'] as int,
        kind: json['kind'] as String,
        location: json['location'] as String,
        label: json['label'] as String?,
        status: json['status'] as String,
        createdAt: json['created_at'] as String,
      );
}
