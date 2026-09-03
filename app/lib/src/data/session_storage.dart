import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Backend-də `GET /auth/me` (sessiya doğrulama endpoint-i) YOXDUR — app
/// saxlanmış token-i birbaşa qorunan endpoint-lərə (məs. `GET /chats`)
/// işlədir, `401` alanda logout edir (dildostu-nun `validateSession`-una
/// bənzər ayrıca yoxlama çağırışı əvəzinə).
abstract class SessionStorage {
  Future<String?> readToken();
  Future<int?> readUserId();
  Future<String?> readDisplayName();
  Future<void> writeSession({
    required String token,
    required int userId,
    required String displayName,
  });
  Future<void> clear();
}

class SecureSessionStorage implements SessionStorage {
  SecureSessionStorage({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _tokenKey = 'masterai.auth.token.v1';
  static const _userIdKey = 'masterai.auth.user_id.v1';
  static const _displayNameKey = 'masterai.auth.display_name.v1';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> readToken() => _storage.read(key: _tokenKey);

  @override
  Future<int?> readUserId() async {
    final raw = await _storage.read(key: _userIdKey);
    return raw == null ? null : int.tryParse(raw);
  }

  @override
  Future<String?> readDisplayName() => _storage.read(key: _displayNameKey);

  @override
  Future<void> writeSession({
    required String token,
    required int userId,
    required String displayName,
  }) async {
    await _storage.write(key: _tokenKey, value: token);
    await _storage.write(key: _userIdKey, value: userId.toString());
    await _storage.write(key: _displayNameKey, value: displayName);
  }

  @override
  Future<void> clear() async {
    await _storage.delete(key: _tokenKey);
    await _storage.delete(key: _userIdKey);
    await _storage.delete(key: _displayNameKey);
  }
}

/// Testlər üçün yaddaşda saxlama.
class InMemorySessionStorage implements SessionStorage {
  String? token;
  int? userId;
  String? displayName;

  @override
  Future<String?> readToken() async => token;

  @override
  Future<int?> readUserId() async => userId;

  @override
  Future<String?> readDisplayName() async => displayName;

  @override
  Future<void> writeSession({
    required String token,
    required int userId,
    required String displayName,
  }) async {
    this.token = token;
    this.userId = userId;
    this.displayName = displayName;
  }

  @override
  Future<void> clear() async {
    token = null;
    userId = null;
    displayName = null;
  }
}
