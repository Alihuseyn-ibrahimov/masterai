import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:masterai/src/data/api_exception.dart';
import 'package:masterai/src/data/auth_client.dart';

String _authResponse({
  String email = 'ali@example.com',
  int id = 1,
  bool isTeacher = false,
  bool isAdmin = false,
}) =>
    jsonEncode({
      'token': 'tok123',
      'user': {
        'id': id,
        'email': email,
        'display_name': 'Əli',
        'created_at': '2026-09-03T00:00:00Z',
        'is_teacher': isTeacher,
        'is_admin': isAdmin,
      },
    });

void main() {
  group('register', () {
    test('uğurlu qeydiyyat token+user qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/auth/register');
        final body = jsonDecode(req.body) as Map<String, dynamic>;
        expect(body['email'], 'ali@example.com');
        expect(body['display_name'], 'Əli');
        // `http.Response(String, int)`-in `encoding` adlı parametri YOXDUR —
        // kodlaşdırma daxili olaraq `headers`-dəki `content-type`-dan
        // törədilir: `application/json` olsa utf8, əks halda (və ya
        // header heç yoxdursa) defolt latin1 (bax `http` paketinin real
        // `response.dart` mənbəyi). Latin1 Azərbaycan hərfləri ilə
        // toqquşduğu üçün bu header AÇIQ göstərilməlidir — bu asimmetriya
        // real `flutter test`-də tapıldı (bax masterai/CLAUDE.md, "Dərs"
        // bölməsi).
        return http.Response(
          _authResponse(),
          201,
          headers: {'content-type': 'application/json'},
        );
      });
      final client = AuthClient(baseUrl: 'https://x', httpClient: mock);
      final result = await client.register(
        email: 'ali@example.com',
        password: 'Parol1234',
        displayName: 'Əli',
      );
      expect(result.token, 'tok123');
      expect(result.user.displayName, 'Əli');
      expect(result.user.isTeacher, false);
      expect(result.user.isAdmin, false);
    });

    test('409 → aydın xəta mesajı', () async {
      final mock = MockClient((req) async => http.Response('{}', 409));
      final client = AuthClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.register(email: 'ali@example.com', password: 'Parol1234', displayName: 'Əli'),
        throwsA(isA<ApiException>().having(
            (e) => e.message, 'message', contains('artıq qeydiyyatdadır'))),
      );
    });

    test('şəbəkə xətası → ApiException (crash yox)', () async {
      final mock = MockClient((req) async => throw Exception('offline'));
      final client = AuthClient(baseUrl: 'https://x', httpClient: mock);
      expect(
        client.register(email: 'a@b.com', password: 'Parol1234', displayName: 'A'),
        throwsA(isA<ApiException>()),
      );
    });
  });

  group('login', () {
    test('uğurlu giriş token qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/auth/login');
        return http.Response(
          _authResponse(),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final client = AuthClient(baseUrl: 'https://x', httpClient: mock);
      final result = await client.login(email: 'ali@example.com', password: 'Parol1234');
      expect(result.token, 'tok123');
    });

    test('401 → aydın xəta mesajı', () async {
      final mock = MockClient((req) async => http.Response('{}', 401));
      final client = AuthClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.login(email: 'ali@example.com', password: 'Səhv'),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('səhvdir'))),
      );
    });
  });
}
