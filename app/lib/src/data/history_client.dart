import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/history.dart';
import 'api_exception.dart';

const _timeout = Duration(seconds: 15);

/// `/history/*` REST-i (Fərdi tələbə tarixçəsi) — canlı sessiya + ev
/// tapşırığı nəticələrini birləşdirilmiş şəkildə qaytarır.
class HistoryClient {
  HistoryClient({required this.baseUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  Future<List<HistoryEntry>> getMyHistory(String token) => _get(token, '/history/me');

  Future<List<HistoryEntry>> getStudentHistory(String token, int studentId) =>
      _get(token, '/history/student/$studentId');

  Future<List<HistoryEntry>> _get(String token, String path) async {
    http.Response resp;
    try {
      resp = await _http
          .get(Uri.parse('$baseUrl$path'), headers: {'Authorization': 'Bearer $token'})
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException(
        resp.statusCode == 403 ? 'Bu tarixçəyə baxmaq icazəniz yoxdur.' : 'Tarixçə yüklənmədi (${resp.statusCode}).',
        statusCode: resp.statusCode,
      );
    }
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((e) => HistoryEntry.fromJson(e as Map<String, dynamic>)).toList();
  }
}
