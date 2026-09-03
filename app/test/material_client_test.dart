import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:masterai/src/data/api_exception.dart';
import 'package:masterai/src/data/material_client.dart';

String _materialResponse({String status = 'processing'}) => jsonEncode({
      'id': 1,
      'chat_id': 5,
      'uploaded_by': 2,
      'kind': 'link',
      'location': 'https://x.az',
      'label': null,
      'status': status,
      'created_at': '2026-09-03T00:00:00Z',
    });

void main() {
  group('uploadLink', () {
    test('multipart sahələri (kind/location) düzgün göndərilir', () async {
      final mock = MockClient.streaming((req, bodyStream) async {
        expect(req, isA<http.MultipartRequest>());
        final multipart = req as http.MultipartRequest;
        expect(multipart.headers['Authorization'], 'Bearer tok');
        expect(multipart.fields['kind'], 'link');
        expect(multipart.fields['location'], 'https://x.az');
        return http.StreamedResponse(Stream.value(utf8.encode(_materialResponse())), 202);
      });
      final client = MaterialClient(baseUrl: 'https://x', httpClient: mock);
      final material = await client.uploadLink('tok', 5, location: 'https://x.az');
      expect(material.status, 'processing');
    });

    test('413 → aydın "çox böyükdür" mesajı', () async {
      final mock = MockClient.streaming(
        (req, bodyStream) async => http.StreamedResponse(Stream.value(utf8.encode('{}')), 413),
      );
      final client = MaterialClient(baseUrl: 'https://x', httpClient: mock);
      await expectLater(
        client.uploadLink('tok', 5, location: 'https://x.az'),
        throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('böyükdür'))),
      );
    });
  });

  group('uploadFile', () {
    test('yerli fayl multipart-a əlavə olunur', () async {
      final tempFile = File('${Directory.systemTemp.path}/masterai_test_upload.pdf');
      await tempFile.writeAsBytes([0x25, 0x50, 0x44, 0x46]); // "%PDF"
      addTearDown(() => tempFile.delete());

      final mock = MockClient.streaming((req, bodyStream) async {
        final multipart = req as http.MultipartRequest;
        expect(multipart.fields['kind'], 'pdf');
        expect(multipart.files.single.field, 'file');
        return http.StreamedResponse(Stream.value(utf8.encode(_materialResponse())), 202);
      });
      final client = MaterialClient(baseUrl: 'https://x', httpClient: mock);
      await client.uploadFile('tok', 5, kind: 'pdf', filePath: tempFile.path);
    });
  });

  group('listMaterials', () {
    test('siyahı parse olunur', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/chats/5/materials');
        return http.Response(jsonEncode([jsonDecode(_materialResponse(status: 'ready'))]), 200);
      });
      final client = MaterialClient(baseUrl: 'https://x', httpClient: mock);
      final materials = await client.listMaterials('tok', 5);
      expect(materials.single.status, 'ready');
    });
  });
}
