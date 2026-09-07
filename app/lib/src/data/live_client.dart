import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/live_question.dart';
import '../models/live_session.dart';
import '../models/question_set.dart';
import 'api_exception.dart';

const _timeout = Duration(seconds: 15);

/// `/live/*` REST-i (host konsolu — mövcud tələbə-yönümlü `/chats/*`
/// axınından ayrı, bax dizayn sənədi). Host konsolu qəsdən yalnız **link**
/// materialını dəstəkləyir — fayl seçimi (`file_picker`) veb build-də
/// yol (path) qaytarmır, bax `masterai/CLAUDE.md`, "Dərs: Flutter app...".
class LiveClient {
  LiveClient({required this.baseUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  Future<QuestionSetInfo> createQuestionSet(
    String token, {
    required String subject,
    required String title,
    required String location,
  }) async {
    http.Response resp;
    try {
      resp = await _http
          .post(
            Uri.parse('$baseUrl/live/question-sets'),
            headers: {'Authorization': 'Bearer $token'},
            body: {'subject': subject, 'title': title, 'kind': 'link', 'location': location},
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 202) {
      throw ApiException(_createErrorFor(resp.statusCode), statusCode: resp.statusCode);
    }
    return QuestionSetInfo.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  Future<List<QuestionSetInfo>> listQuestionSets(String token) async {
    final resp = await _get(token, '/live/question-sets');
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((q) => QuestionSetInfo.fromJson(q as Map<String, dynamic>)).toList();
  }

  Future<QuestionSetInfo> getQuestionSet(String token, int id) async {
    final resp = await _get(token, '/live/question-sets/$id');
    return QuestionSetInfo.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  Future<LiveSessionInfo> createLiveSession(String token, int questionSetId) async {
    http.Response resp;
    try {
      resp = await _http
          .post(
            Uri.parse('$baseUrl/live/sessions'),
            headers: {'Authorization': 'Bearer $token', 'Content-Type': 'application/json'},
            body: jsonEncode({'question_set_id': questionSetId}),
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 201) {
      throw ApiException(
        resp.statusCode == 400 ? 'Sual bankı hələ hazır deyil.' : 'Sessiya yaradıla bilmədi (${resp.statusCode}).',
        statusCode: resp.statusCode,
      );
    }
    return LiveSessionInfo.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  Future<LiveSessionReport> getReport(String token, int sessionId) async {
    final resp = await _get(token, '/live/sessions/$sessionId/report');
    return LiveSessionReport.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  /// Sual bankının BÜTÜN suallarının TAM məzmunu (düzgün cavab+izah
  /// daxil) — yalnız müəllim redaktə ekranı üçün (bax Sual redaktə/
  /// təsdiq ekranı, Faza 5).
  Future<List<LiveQuestionInfo>> listQuestions(String token, int questionSetId) async {
    final resp = await _get(token, '/live/question-sets/$questionSetId/questions');
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((q) => LiveQuestionInfo.fromJson(q as Map<String, dynamic>)).toList();
  }

  Future<LiveQuestionInfo> updateQuestion(
    String token,
    int questionId, {
    required String question,
    required List<String> options,
    required int correctIndex,
    required String explanation,
  }) async {
    http.Response resp;
    try {
      resp = await _http
          .patch(
            Uri.parse('$baseUrl/live/questions/$questionId'),
            headers: {'Authorization': 'Bearer $token', 'Content-Type': 'application/json'},
            body: jsonEncode({
              'question': question,
              'options': options,
              'correct_index': correctIndex,
              'explanation': explanation,
            }),
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException('Sual yenilənmədi (${resp.statusCode}).', statusCode: resp.statusCode);
    }
    return LiveQuestionInfo.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  Future<void> deleteQuestion(String token, int questionId) async {
    http.Response resp;
    try {
      resp = await _http
          .delete(
            Uri.parse('$baseUrl/live/questions/$questionId'),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 204) {
      throw ApiException('Sual silinmədi (${resp.statusCode}).', statusCode: resp.statusCode);
    }
  }

  Future<http.Response> _get(String token, String path) async {
    http.Response resp;
    try {
      resp = await _http
          .get(Uri.parse('$baseUrl$path'), headers: {'Authorization': 'Bearer $token'})
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException('Sorğu uğursuz oldu (${resp.statusCode}).', statusCode: resp.statusCode);
    }
    return resp;
  }

  String _createErrorFor(int statusCode) {
    switch (statusCode) {
      case 400:
        return 'Fənn/link sahələrini yoxlayın.';
      default:
        return 'Sual bankı yaradıla bilmədi ($statusCode).';
    }
  }
}
