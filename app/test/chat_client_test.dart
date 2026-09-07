import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:masterai/src/data/api_exception.dart';
import 'package:masterai/src/data/chat_client.dart';

// Bax `masterai/CLAUDE.md`, "Dərs: Flutter app..." — `http.Response`-un
// kodlaşdırması `content-type` header-indən törəyir, Azərbaycan hərfləri
// olan fixture-larda bu HƏMİŞƏ açıq göstərilməlidir.
const _jsonHeaders = {'content-type': 'application/json'};

void main() {
  group('listChats', () {
    test('token Authorization başlığında göndərilir, siyahı parse olunur', () async {
      final mock = MockClient((req) async {
        expect(req.headers['Authorization'], 'Bearer tok123');
        expect(req.url.path, '/chats');
        return http.Response(
          jsonEncode([
            {
              'id': 1,
              'kind': 'group',
              'name': 'Qrup',
              'created_by': 1,
              'created_at': '2026-09-03T00:00:00Z',
            },
          ]),
          200,
        );
      });
      final client = ChatClient(baseUrl: 'https://x', httpClient: mock);
      final chats = await client.listChats('tok123');
      expect(chats, hasLength(1));
      expect(chats.single.name, 'Qrup');
    });

    test('401 → ApiException (statusCode daxil)', () async {
      final mock = MockClient((req) async => http.Response('{}', 401));
      final client = ChatClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.listChats('köhnə-token'),
        throwsA(isA<ApiException>().having((e) => e.statusCode, 'statusCode', 401)),
      );
    });
  });

  group('createGroupChat', () {
    test('kind=group body-si göndərilir', () async {
      final mock = MockClient((req) async {
        final body = jsonDecode(req.body) as Map<String, dynamic>;
        expect(body['kind'], 'group');
        expect(body['name'], 'Yeni qrup');
        return http.Response(
          jsonEncode({
            'id': 5,
            'kind': 'group',
            'name': 'Yeni qrup',
            'created_by': 1,
            'created_at': '2026-09-03T00:00:00Z',
          }),
          201,
        );
      });
      final client = ChatClient(baseUrl: 'https://x', httpClient: mock);
      final chat = await client.createGroupChat('tok', name: 'Yeni qrup');
      expect(chat.id, 5);
    });
  });

  group('joinChat', () {
    test('uğurlu qoşulma çatı qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.method, 'POST');
        expect(req.url.path, '/chats/3/join');
        return http.Response(
          jsonEncode({
            'id': 3,
            'kind': 'group',
            'name': 'Qrup',
            'created_by': 2,
            'created_at': '2026-09-03T00:00:00Z',
          }),
          200,
        );
      });
      final client = ChatClient(baseUrl: 'https://x', httpClient: mock);
      final chat = await client.joinChat('tok', 3);
      expect(chat.id, 3);
    });

    test('404 → aydın xəta mesajı', () async {
      final mock = MockClient((req) async => http.Response('{}', 404));
      final client = ChatClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.joinChat('tok', 999),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('tapılmadı'))),
      );
    });
  });

  group('listMembers', () {
    test('üzv siyahısını qaytarır', () async {
      final mock = MockClient((req) async {
        expect(req.method, 'GET');
        expect(req.url.path, '/chats/3/members');
        return http.Response(
          jsonEncode([
            {'user_id': 1, 'display_name': 'Müəllim'},
            {'user_id': 2, 'display_name': 'Tələbə'},
          ]),
          200,
          headers: _jsonHeaders,
        );
      });
      final client = ChatClient(baseUrl: 'https://x', httpClient: mock);
      final members = await client.listMembers('tok', 3);
      expect(members, hasLength(2));
      expect(members[1].displayName, 'Tələbə');
    });

    test('403 → ApiException', () async {
      final mock = MockClient((req) async => http.Response('{}', 403));
      final client = ChatClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(client.listMembers('tok', 3), throwsA(isA<ApiException>()));
    });
  });
}
