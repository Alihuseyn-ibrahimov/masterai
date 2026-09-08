import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

/// `WS /ws/live/{pin}/host` sarğısı. `ChatSocket`-dən fərqli olaraq
/// hadisə növləri az və sadədir (`state`/`participant_joined`/`started`/
/// `participant_progress`/`finished`) — sealed model əvəzinə xam
/// `Map<String, dynamic>` axını kifayətdir, UI `event['type']`-ə görə
/// seçim edir. Fərdi templi modeldə (bax `.planning/2026-09-08-masterai-
/// live-session-pacing/`) host artıq paylaşılan `question`/`result`
/// hadisələrini ALMIR — hər tələbə öz sualını/nəticəsini birbaşa özü
/// görür, host yalnız hər kəsin FƏRDİ tərəqqisini (`participant_progress`)
/// izləyir.
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

  /// `durationSeconds` — sessiyanın ÜMUMİ vaxt büdcəsi (bax dizayn qərarı,
  /// `.planning/2026-09-08-masterai-live-session-pacing/`). Müəllimin
  /// mənual "Növbəti sual" ("next" action) artıq YOXDUR — hər tələbə öz
  /// sürəti ilə özü irəliləyir.
  void sendStart({required int durationSeconds}) {
    _channel?.sink.add(jsonEncode({'action': 'start', 'duration_seconds': durationSeconds}));
  }

  Future<void> dispose() async {
    await _subscription?.cancel();
    await _channel?.sink.close();
    await _eventsController.close();
    await _errorController.close();
    await _disconnectController.close();
  }
}
