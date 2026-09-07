import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:masterai/src/data/admin_client.dart';
import 'package:masterai/src/data/api_exception.dart';

const _jsonHeaders = {'content-type': 'application/json'};

Map<String, dynamic> _userJson({bool isTeacher = true}) => {
      'id': 2,
      'email': 'aygun@masternr1.az',
      'display_name': 'Aygün',
      'created_at': '2026-09-07T00:00:00Z',
      'is_teacher': isTeacher,
      'is_admin': false,
    };

void main() {
  group('setTeacherRole', () {
    test('uğurlu çağırış yenilənmiş UserInfo qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.method, 'POST');
        expect(req.url.path, '/admin/teachers');
        final body = jsonDecode(req.body) as Map<String, dynamic>;
        expect(body['email'], 'aygun@masternr1.az');
        expect(body['is_teacher'], true);
        return http.Response(jsonEncode(_userJson()), 200, headers: _jsonHeaders);
      });
      final client = AdminClient(baseUrl: 'https://x', httpClient: mock);
      final user = await client.setTeacherRole('tok', email: 'aygun@masternr1.az', isTeacher: true);
      expect(user.isTeacher, true);
      expect(user.displayName, 'Aygün');
    });

    test('403 → ApiException', () async {
      final mock = MockClient((req) async => http.Response('{}', 403));
      final client = AdminClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.setTeacherRole('tok', email: 'x@x.az', isTeacher: true),
        throwsA(isA<ApiException>()),
      );
    });

    test('404 → aydın xəta mesajı', () async {
      final mock = MockClient((req) async => http.Response('{}', 404));
      final client = AdminClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.setTeacherRole('tok', email: 'yoxdur@x.az', isTeacher: true),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('tapılmadı'))),
      );
    });
  });
}
