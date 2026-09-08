import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/material.dart';
import 'api_exception.dart';

const _timeout = Duration(seconds: 30); // yükləmə üçün auth-dan uzun

/// `/chats/{id}/materials` REST-i (multipart yükləmə).
class MaterialClient {
  MaterialClient({required this.baseUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  Future<List<MaterialInfo>> listMaterials(String token, int chatId) async {
    http.Response resp;
    try {
      resp = await _http
          .get(
            Uri.parse('$baseUrl/chats/$chatId/materials'),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException(
        'Materiallar yüklənmədi (${resp.statusCode}).',
        statusCode: resp.statusCode,
      );
    }
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((m) => MaterialInfo.fromJson(m as Map<String, dynamic>)).toList();
  }

  /// Link materialı — `location` sayt ünvanıdır, fayl yoxdur.
  /// `questionCount` — müəllimin istədiyi ÜMUMİ sual sayı (3-30, bax
  /// `server/app.py`, `_MIN_QUESTION_COUNT`/`_MAX_QUESTION_COUNT`).
  Future<MaterialInfo> uploadLink(
    String token,
    int chatId, {
    required String location,
    String? label,
    int questionCount = 10,
  }) =>
      _upload(token, chatId, kind: 'link', location: location, label: label, questionCount: questionCount);

  /// PDF/şəkil materialı — `filePath` yerli fayl yoludur (`file_picker`-dən).
  Future<MaterialInfo> uploadFile(
    String token,
    int chatId, {
    required String kind, // "pdf" | "image"
    required String filePath,
    String? label,
    int questionCount = 10,
  }) =>
      _upload(token, chatId, kind: kind, filePath: filePath, label: label, questionCount: questionCount);

  Future<MaterialInfo> _upload(
    String token,
    int chatId, {
    required String kind,
    String? location,
    String? filePath,
    String? label,
    int questionCount = 10,
  }) async {
    final uri = Uri.parse('$baseUrl/chats/$chatId/materials');
    final request = http.MultipartRequest('POST', uri)
      ..headers['Authorization'] = 'Bearer $token'
      ..fields['kind'] = kind
      ..fields['question_count'] = '$questionCount';
    if (location != null) request.fields['location'] = location;
    if (label != null) request.fields['label'] = label;
    if (filePath != null) {
      request.files.add(await http.MultipartFile.fromPath('file', filePath));
    }

    http.StreamedResponse streamed;
    try {
      streamed = await _http.send(request).timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    final resp = await http.Response.fromStream(streamed);

    if (resp.statusCode != 202) {
      throw ApiException(_messageFor(resp.statusCode), statusCode: resp.statusCode);
    }
    return MaterialInfo.fromJson(jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>);
  }

  String _messageFor(int statusCode) {
    switch (statusCode) {
      case 400:
        return 'Material üçün lazımi sahə əskikdir (link/fayl).';
      case 403:
        return 'Bu çatın üzvü deyilsiniz.';
      case 404:
        return 'Çat tapılmadı.';
      case 413:
        return 'Fayl çox böyükdür (maks. 20 MB).';
      default:
        return 'Material yüklənmədi ($statusCode). Yenidən cəhd et.';
    }
  }
}
