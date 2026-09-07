class ChatInfo {
  final int id;
  final String kind; // "direct" | "group"
  final String? name;
  final int createdBy;
  final String createdAt;

  const ChatInfo({
    required this.id,
    required this.kind,
    required this.name,
    required this.createdBy,
    required this.createdAt,
  });

  factory ChatInfo.fromJson(Map<String, dynamic> json) => ChatInfo(
        id: json['id'] as int,
        kind: json['kind'] as String,
        name: json['name'] as String?,
        createdBy: json['created_by'] as int,
        createdAt: json['created_at'] as String,
      );
}

/// `GET /chats/{id}/members` sətri — müəllimin Fərdi tələbə tarixçəsi
/// ekranında tələbə seçmək üçün istifadə olunur.
class ChatMemberInfo {
  final int userId;
  final String displayName;

  const ChatMemberInfo({required this.userId, required this.displayName});

  factory ChatMemberInfo.fromJson(Map<String, dynamic> json) => ChatMemberInfo(
        userId: json['user_id'] as int,
        displayName: json['display_name'] as String,
      );
}
