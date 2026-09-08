import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/badge.dart';
import 'api_exception.dart';

const _timeout = Duration(seconds: 10);

/// `/badges/*` REST-i (Faza 6 — Nailiyyət nişanları).
class BadgeClient {
  BadgeClient({required this.baseUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  Future<List<BadgeInfo>> getMyBadges(String token) async {
    http.Response resp;
    try {
      resp = await _http
          .get(Uri.parse('$baseUrl/badges/me'), headers: {'Authorization': 'Bearer $token'})
          .timeout(_timeout);
    } catch (_) {
      throw const ApiException(kNetworkErrorMessage);
    }
    if (resp.statusCode != 200) {
      throw ApiException('Nişanlar yüklənmədi (${resp.statusCode}).', statusCode: resp.statusCode);
    }
    final list = jsonDecode(utf8.decode(resp.bodyBytes)) as List;
    return list.map((b) => BadgeInfo.fromJson(b as Map<String, dynamic>)).toList();
  }
}
