import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/user.dart';
import 'api_exception.dart';

const _timeout = Duration(seconds: 10);

/// `/admin/teachers` REST-i — Çox-müəllimli idarəetmə (Faza 4). Yalnız
/// `is_admin` istifadəçilər çağıra bilər (bax `server/app.py`,
/// `set_teacher_role`); İLK admin VPS-də əl ilə təyin edilir.
class AdminClient {
  AdminClient({required this.baseUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  Future<UserInfo> setTeacherRole(String token, {required String email, required bool isTeacher}) async {
    http.Response resp;
    try {
      resp = await _http
          .post(
            Uri.parse('$baseUrl/admin/teachers'),
            headers: {'Authorization': 'Bearer $token', 'Content-Type': 'application/json'},
            body: jsonEncode({'email': email, 'is_teacher': isTeacher}),
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException(
        resp.statusCode == 404 ? 'Bu e-poçtla istifadəçi tapılmadı.' : 'Əməliyyat uğursuz oldu (${resp.statusCode}).',
        statusCode: resp.statusCode,
      );
    }
    return UserInfo.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }
}
