import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

/// `WS /ws/live/{pin}/play` sarğısı — tələbə tərəfi. `LiveHostSocket`-dən
/// fərqli olaraq token YOXDUR (qeydiyyatsız qoşulma, bax dizayn sənədi);
/// bunun əvəzinə bağlantı açılan kimi İLK mesaj kimi `display_name`
/// göndərilməlidir (bax `server/app.py`, `live_play_websocket`).
///
/// Qoşulma rədd edilərsə (naməlum PIN, artıq başlamış/bitmiş sessiya,
/// format xətası) server heç bir JSON mesajı göndərmədən bağlantını
/// bağlayır (`4400`/`4404`/`4409` close code-ları) — bu, `onDisconnected`
/// kimi görünür, `LiveHostSocket`-in eyni sadələşdirməsinə bənzər
/// (aydın xəta mesajı yoxdur, ekran ümumi "qoşulma alınmadı" göstərir).
class LivePlaySocket {
  LivePlaySocket({required String wsBaseUrl, required String pin, required String displayName})
      : _uri = Uri.parse('$wsBaseUrl/ws/live/$pin/play'),
        _displayName = displayName;

  final Uri _uri;
  final String _displayName;
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;

  final _eventsController = StreamController<Map<String, dynamic>>.broadcast();
  final _errorController = StreamController<String>.broadcast();
  final _disconnectController = StreamController<void>.broadcast();

  /// `joined`/`question`/`result`/`finished` hadisələri.
  Stream<Map<String, dynamic>> get events => _eventsController.stream;

  /// Aktiv sessiyada baş verən xətalar (məs. `AlreadyAnswered`) —
  /// qoşulma rəddi BURADA GəLMİR, bax sinif qeydi.
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
    channel.sink.add(jsonEncode({'display_name': _displayName}));
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

  void sendAnswer({required int questionIndex, required int chosenIndex}) {
    _channel?.sink.add(jsonEncode({
      'type': 'answer',
      'question_index': questionIndex,
      'chosen_index': chosenIndex,
    }));
  }

  Future<void> dispose() async {
    await _subscription?.cancel();
    await _channel?.sink.close();
    await _eventsController.close();
    await _errorController.close();
    await _disconnectController.close();
  }
}
