class UserInfo {
  final int id;
  final String email;
  final String displayName;
  final String createdAt;
  final bool isTeacher;
  final bool isAdmin;

  const UserInfo({
    required this.id,
    required this.email,
    required this.displayName,
    required this.createdAt,
    required this.isTeacher,
    required this.isAdmin,
  });

  factory UserInfo.fromJson(Map<String, dynamic> json) => UserInfo(
        id: json['id'] as int,
        email: json['email'] as String,
        displayName: json['display_name'] as String,
        createdAt: json['created_at'] as String,
        isTeacher: json['is_teacher'] as bool,
        isAdmin: json['is_admin'] as bool,
      );
}

class AuthResponse {
  final String token;
  final UserInfo user;

  const AuthResponse({required this.token, required this.user});

  factory AuthResponse.fromJson(Map<String, dynamic> json) => AuthResponse(
        token: json['token'] as String,
        user: UserInfo.fromJson(json['user'] as Map<String, dynamic>),
      );
}
