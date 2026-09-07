import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/homework.dart';
import 'api_exception.dart';

const _timeout = Duration(seconds: 15);

/// `/homework/*` REST-i (Ev təkrarı rejimi, Faza 2) — WebSocket YOXDUR,
/// asinxron tək-oyunçulu axın (bax dizayn sənədi).
class HomeworkClient {
  HomeworkClient({required this.baseUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  Future<HomeworkAssignmentInfo> createAssignment(
    String token, {
    required int chatId,
    required int questionSetId,
    required String dueDate,
  }) async {
    http.Response resp;
    try {
      resp = await _http
          .post(
            Uri.parse('$baseUrl/homework/assignments'),
            headers: {'Authorization': 'Bearer $token', 'Content-Type': 'application/json'},
            body: jsonEncode({
              'chat_id': chatId,
              'question_set_id': questionSetId,
              'due_date': dueDate,
            }),
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 201) {
      throw ApiException(
        resp.statusCode == 400 ? 'Sual bankı hələ hazır deyil.' : 'Tapşırıq yaradıla bilmədi (${resp.statusCode}).',
        statusCode: resp.statusCode,
      );
    }
    return HomeworkAssignmentInfo.fromJson(
      jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>,
    );
  }

  Future<List<HomeworkAssignmentInfo>> listAssignments(String token, {required int chatId}) async {
    final resp = await _get(token, '/homework/assignments?chat_id=$chatId');
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((a) => HomeworkAssignmentInfo.fromJson(a as Map<String, dynamic>)).toList();
  }

  Future<List<HomeworkReportRow>> getReport(String token, int assignmentId) async {
    final resp = await _get(token, '/homework/assignments/$assignmentId/report');
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((r) => HomeworkReportRow.fromJson(r as Map<String, dynamic>)).toList();
  }

  Future<List<MyAssignmentInfo>> listMyAssignments(String token) async {
    final resp = await _get(token, '/homework/my-assignments');
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((a) => MyAssignmentInfo.fromJson(a as Map<String, dynamic>)).toList();
  }

  Future<HomeworkAttemptState> startAttempt(String token, int assignmentId) async {
    http.Response resp;
    try {
      resp = await _http
          .post(
            Uri.parse('$baseUrl/homework/assignments/$assignmentId/start'),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException('Tapşırıq başladıla bilmədi (${resp.statusCode}).', statusCode: resp.statusCode);
    }
    return HomeworkAttemptState.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  Future<HomeworkAnswerResult> answer(
    String token, {
    required int attemptId,
    required int questionIndex,
    required int chosenIndex,
  }) async {
    http.Response resp;
    try {
      resp = await _http
          .post(
            Uri.parse('$baseUrl/homework/attempts/$attemptId/answer'),
            headers: {'Authorization': 'Bearer $token', 'Content-Type': 'application/json'},
            body: jsonEncode({'question_index': questionIndex, 'chosen_index': chosenIndex}),
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException('Cavab göndərilmədi (${resp.statusCode}).', statusCode: resp.statusCode);
    }
    return HomeworkAnswerResult.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
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
}
