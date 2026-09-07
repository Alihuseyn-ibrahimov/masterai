import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

/// `WS /ws/live/{pin}/host` sarğısı. `ChatSocket`-dən fərqli olaraq
/// hadisə növləri az və sadədir (`state`/`participant_joined`/`question`/
/// `answer_progress`/`result`/`finished`) — sealed model əvəzinə xam
/// `Map<String, dynamic>` axını kifayətdir, UI `event['type']`-ə görə
/// seçim edir.
///
/// Eyni bilinən risk `ChatSocket`-də olduğu kimi keçərlidir: token query
/// param-dadır (bax `masterai/CLAUDE.md`, "Bilinən risklər").
class LiveHostSocket {
  LiveHostSocket({required String wsBaseUrl, required String pin, required String token})
      : _uri = Uri.parse('$wsBaseUrl/ws/live/$pin/host?token=$token');

  final Uri _uri;
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;

  final _eventsController = StreamController<Map<String, dynamic>>.broadcast();
  final _errorController = StreamController<String>.broadcast();
  final _disconnectController = StreamController<void>.broadcast();

  Stream<Map<String, dynamic>> get events => _eventsController.stream;
  Stream<String> get errors => _errorController.stream;
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
      return; // format səhvi — sükutla keç
    }
    if (event['type'] == 'error') {
      _errorController.add(event['detail'] as String? ?? 'naməlum xəta');
      return;
    }
    _eventsController.add(event);
  }

  void sendStart() {
    _channel?.sink.add(jsonEncode({'action': 'start'}));
  }

  void sendNext() {
    _channel?.sink.add(jsonEncode({'action': 'next'}));
  }

  Future<void> dispose() async {
    await _subscription?.cancel();
    await _channel?.sink.close();
    await _eventsController.close();
    await _errorController.close();
    await _disconnectController.close();
  }
}
