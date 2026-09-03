import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:masterai/src/data/api_exception.dart';
import 'package:masterai/src/data/auth_client.dart';

String _authResponse({String email = 'ali@example.com', int id = 1}) => jsonEncode({
      'token': 'tok123',
      'user': {
        'id': id,
        'email': email,
        'display_name': 'Əli',
        'created_at': '2026-09-03T00:00:00Z',
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
        return http.Response(_authResponse(), 201);
      });
      final client = AuthClient(baseUrl: 'https://x', httpClient: mock);
      final result = await client.register(
        email: 'ali@example.com',
        password: 'Parol1234',
        displayName: 'Əli',
      );
      expect(result.token, 'tok123');
      expect(result.user.displayName, 'Əli');
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
        return http.Response(_authResponse(), 200);
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
