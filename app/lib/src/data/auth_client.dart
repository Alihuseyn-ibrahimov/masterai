import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/user.dart';
import 'api_exception.dart';

const _timeout = Duration(seconds: 10);

/// Server-in `/auth/*` endpoint-ləri ilə danışan qat (dildostu-nun
/// `AuthClient` naxışı).
class AuthClient {
  AuthClient({required this.baseUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  Future<AuthResponse> register({
    required String email,
    required String password,
    required String displayName,
  }) =>
      _authRequest('/auth/register', {
        'email': email,
        'password': password,
        'display_name': displayName,
      });

  Future<AuthResponse> login({
    required String email,
    required String password,
  }) =>
      _authRequest('/auth/login', {'email': email, 'password': password});

  Future<AuthResponse> _authRequest(String path, Map<String, dynamic> body) async {
    http.Response resp;
    try {
      resp = await _http
          .post(
            Uri.parse('$baseUrl$path'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }

    if (resp.statusCode == 200 || resp.statusCode == 201) {
      return AuthResponse.fromJson(
        jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>,
      );
    }
    throw ApiException(_messageFor(resp.statusCode), statusCode: resp.statusCode);
  }

  String _messageFor(int statusCode) {
    switch (statusCode) {
      case 409:
        return 'Bu e-poçt artıq qeydiyyatdadır. Giriş etməyi sınayın.';
      case 401:
        return 'E-poçt və ya şifrə səhvdir.';
      case 422:
        return 'E-poçt düzgün deyil, şifrə qısadır (min. 8 simvol) və ya ad boşdur.';
      default:
        return 'Xəta baş verdi ($statusCode). Yenidən cəhd et.';
    }
  }
}
