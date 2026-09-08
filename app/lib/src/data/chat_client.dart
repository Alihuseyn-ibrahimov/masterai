import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/chat.dart';
import '../models/leaderboard.dart';
import 'api_exception.dart';

const _timeout = Duration(seconds: 10);

/// `/chats` REST-i. Token hər çağırışa ötürülür (client daxili sessiya
/// saxlamır — bax `session_storage.dart`).
class ChatClient {
  ChatClient({required this.baseUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  Future<List<ChatInfo>> listChats(String token) async {
    http.Response resp;
    try {
      resp = await _http
          .get(
            Uri.parse('$baseUrl/chats'),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException('Çatlar yüklənmədi (${resp.statusCode}).', statusCode: resp.statusCode);
    }
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((c) => ChatInfo.fromJson(c as Map<String, dynamic>)).toList();
  }

  /// Yalnız qrup çatı yaradır (MVP-də `direct` üçün UI yoxdur — backend
  /// `kind="direct"` dostluq tələb edir, bax `friendship_store.py`).
  Future<ChatInfo> createGroupChat(String token, {required String name}) async {
    http.Response resp;
    try {
      resp = await _http
          .post(
            Uri.parse('$baseUrl/chats'),
            headers: {
              'Authorization': 'Bearer $token',
              'Content-Type': 'application/json',
            },
            body: jsonEncode({'kind': 'group', 'name': name}),
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 201) {
      throw ApiException('Çat yaradıla bilmədi (${resp.statusCode}).', statusCode: resp.statusCode);
    }
    return ChatInfo.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  /// Mövcud bir qrup çatına özü-özünə qoşulur (`POST /chats/{id}/join`)
  /// — müəllim çat ID-sini tələbələrə ayrıca bildirir (məs. WhatsApp
  /// qrupunda), bax `masterai/CLAUDE.md`, "Ev Təkrarı Rejimi" bölməsi.
  Future<ChatInfo> joinChat(String token, int chatId) async {
    http.Response resp;
    try {
      resp = await _http
          .post(
            Uri.parse('$baseUrl/chats/$chatId/join'),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException(
        resp.statusCode == 404 ? 'Bu ID ilə çat tapılmadı.' : 'Çata qoşulmaq mümkün olmadı (${resp.statusCode}).',
        statusCode: resp.statusCode,
      );
    }
    return ChatInfo.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  /// Çatın üzv siyahısı — Fərdi tələbə tarixçəsi ekranında müəllimin
  /// tələbə seçməsi üçün (bax `history_client.dart`).
  Future<List<ChatMemberInfo>> listMembers(String token, int chatId) async {
    http.Response resp;
    try {
      resp = await _http
          .get(
            Uri.parse('$baseUrl/chats/$chatId/members'),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException('Üzvlər yüklənmədi (${resp.statusCode}).', statusCode: resp.statusCode);
    }
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((m) => ChatMemberInfo.fromJson(m as Map<String, dynamic>)).toList();
  }

  /// Çatın liderlik lövhəsi — yalnız ev tapşırığı xalları (bax Faza 6
  /// dizayn sənədi).
  Future<List<LeaderboardRow>> getLeaderboard(String token, int chatId) async {
    http.Response resp;
    try {
      resp = await _http
          .get(
            Uri.parse('$baseUrl/chats/$chatId/leaderboard'),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException('Liderlik lövhəsi yüklənmədi (${resp.statusCode}).', statusCode: resp.statusCode);
    }
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((r) => LeaderboardRow.fromJson(r as Map<String, dynamic>)).toList();
  }
}
