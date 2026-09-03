import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/quiz_session.dart';
import 'api_exception.dart';

const _timeout = Duration(seconds: 10);

/// `/chats/{id}/quiz/start` REST-i. Nəticə (suallar, cavablar, bitmə)
/// WebSocket üzərindən gəlir (bax `chat_socket.dart`) — bu client yalnız
/// başlatma çağırışıdır.
class QuizClient {
  QuizClient({required this.baseUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  Future<QuizSessionInfo> startQuiz(String token, int chatId, {required int materialId}) async {
    http.Response resp;
    try {
      resp = await _http
          .post(
            Uri.parse('$baseUrl/chats/$chatId/quiz/start'),
            headers: {
              'Authorization': 'Bearer $token',
              'Content-Type': 'application/json',
            },
            body: jsonEncode({'material_id': materialId}),
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 201) {
      throw ApiException(_messageFor(resp.statusCode), statusCode: resp.statusCode);
    }
    return QuizSessionInfo.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  String _messageFor(int statusCode) {
    switch (statusCode) {
      case 403:
        return 'Yalnız materialı yükləyən quiz başlada bilər.';
      case 404:
        return 'Material tapılmadı.';
      case 409:
        return 'Bu çatda artıq aktiv quiz var.';
      case 400:
        return 'Material hələ hazır deyil və ya bu çata aid deyil.';
      default:
        return 'Quiz başladıla bilmədi ($statusCode). Yenidən cəhd et.';
    }
  }
}
