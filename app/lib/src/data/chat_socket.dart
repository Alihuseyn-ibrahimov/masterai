import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/chat_item.dart';

/// `WS /ws/chat/{id}` sarğısı — `history`-ni `ChatItem` axınına çevirir,
/// canlı hadisələri eyni axına əlavə edir.
///
/// **Bilinən risk (bax `masterai/CLAUDE.md`, "Bilinən risklər"):** token
/// query param-da göndərilir (`?token=...`) — brauzer WebSocket API-si
/// custom header dəstəkləmədiyi üçün. Mobil app-da bu risk yoxdur (heç bir
/// paylaşılan/loglanan brauzer network paneli), amma server access
/// log-larında token görünə bilər.
///
/// **Avtomatik yenidən qoşulma YOXDUR (MVP məhdudiyyəti)** — bağlantı
/// kəsilsə `onDisconnected` çağırılır, ekran istifadəçiyə "yenidən qoşul"
/// düyməsi göstərməlidir.
class ChatSocket {
  ChatSocket({required String wsBaseUrl, required int chatId, required String token})
      : _uri = Uri.parse('$wsBaseUrl/ws/chat/$chatId?token=$token');

  final Uri _uri;
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;

  final _itemsController = StreamController<ChatItem>.broadcast();
  final _errorController = StreamController<String>.broadcast();
  final _disconnectController = StreamController<void>.broadcast();

  /// Tarixçə (`history`) sətirləri VƏ canlı hadisələr — eyni axın, UI
  /// ikisini fərqləndirmək məcburiyyətində deyil.
  Stream<ChatItem> get items => _itemsController.stream;

  /// Server-in göndərdiyi `{"type":"error","detail":...}` mesajları
  /// (yanlış format, quiz qaydası pozuntusu və s.).
  Stream<String> get errors => _errorController.stream;

  /// Bağlantı hər hansı səbəbdən (auth/üzvlük rəddi, şəbəkə) bağlananda.
  Stream<void> get onDisconnected => _disconnectController.stream;

  void connect() {
    final channel = WebSocketChannel.connect(_uri);
    _channel = channel;
    _subscription = channel.stream.listen(
      _handleRaw,
      onError: (_) => _disconnectController.add(null),
      onDone: () => _disconnectController.add(null),
    );
  }

  void _handleRaw(dynamic raw) {
    final Map<String, dynamic> event;
    try {
      event = jsonDecode(raw as String) as Map<String, dynamic>;
    } catch (_) {
      return; // format səhvi — sükutla keç, bağlantını kəsmə
    }

    final type = event['type'] as String?;
    if (type == 'history') {
      final rows = (event['messages'] as List).cast<Map<String, dynamic>>();
      for (final row in rows) {
        _itemsController.add(ChatItem.fromHistoryRow(row));
      }
      return;
    }
    if (type == 'error') {
      _errorController.add(event['detail'] as String? ?? 'naməlum xəta');
      return;
    }
    final item = type == null ? null : ChatItem.fromLiveEvent(event);
    if (item != null) _itemsController.add(item);
  }

  void sendText(String content) {
    _channel?.sink.add(jsonEncode({'type': 'text', 'content': content}));
  }

  void sendAnswer({required int questionId, required int chosenIndex}) {
    _channel?.sink.add(jsonEncode({
      'type': 'answer',
      'question_id': questionId,
      'chosen_index': chosenIndex,
    }));
  }

  Future<void> dispose() async {
    await _subscription?.cancel();
    await _channel?.sink.close();
    await _itemsController.close();
    await _errorController.close();
    await _disconnectController.close();
  }
}
