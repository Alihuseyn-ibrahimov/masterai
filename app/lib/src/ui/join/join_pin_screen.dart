import 'dart:async';

import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/live_play_socket.dart';
import 'student_session_screen.dart';

/// Tələbənin canlı sinif sessiyasına qoşulma ekranı — heç bir hesab
/// tələb etmir (bax dizayn sənədi, "Tələbə tərəfi"). Giriş ekranından
/// VƏ ya (daxil olmuş istifadəçi üçün) çat siyahısından bir düymə ilə
/// açılır.
///
/// `token` KÖNÜLLÜDÜR — yalnız daxil olmuş istifadəçi bu ekranı
/// `ChatListScreen`-dən açanda dolur (bax `chat_list_screen.dart`), giriş
/// ekranından əvvəlki (hesabsız) qoşulmada `null` qalır. Doldurulanda
/// Fərdi tələbə tarixçəsi bu iştirakı həmin hesaba bağlayır.
class JoinPinScreen extends StatefulWidget {
  const JoinPinScreen({super.key, this.token});

  final String? token;

  @override
  State<JoinPinScreen> createState() => _JoinPinScreenState();
}

class _JoinPinScreenState extends State<JoinPinScreen> {
  final _formKey = GlobalKey<FormState>();
  final _pinController = TextEditingController();
  final _nameController = TextEditingController();

  bool _connecting = false;
  String? _error;

  @override
  void dispose() {
    _pinController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _connecting = true;
      _error = null;
    });

    final socket = LivePlaySocket(
      wsBaseUrl: kWsBaseUrl,
      pin: _pinController.text.trim(),
      displayName: _nameController.text.trim(),
      token: widget.token,
    );

    final joinedCompleter = Completer<Map<String, dynamic>>();
    final eventsSub = socket.events.listen((event) {
      if (event['type'] == 'joined' && !joinedCompleter.isCompleted) {
        joinedCompleter.complete(event);
      }
    });
    final discSub = socket.onDisconnected.listen((_) {
      if (!joinedCompleter.isCompleted) {
        joinedCompleter.completeError(StateError('disconnected'));
      }
    });

    socket.connect();

    try {
      final joined = await joinedCompleter.future.timeout(const Duration(seconds: 10));
      await eventsSub.cancel();
      await discSub.cancel();
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => StudentSessionScreen(
          socket: socket,
          participantId: joined['participant_id'] as int,
          displayName: _nameController.text.trim(),
        ),
      ));
    } catch (_) {
      await eventsSub.cancel();
      await discSub.cancel();
      await socket.dispose();
      if (!mounted) return;
      setState(() {
        _connecting = false;
        _error = 'Qoşulmaq mümkün olmadı — PIN-i yoxlayın (sessiya artıq başlamış/bitmiş ola bilər).';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sinif sessiyasına qoşul')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.groups, size: 64, color: Color(0xFF2F6FED)),
                  const SizedBox(height: 12),
                  Text(
                    'Müəllimin verdiyi PIN-i daxil edin',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 24),
                  TextFormField(
                    controller: _pinController,
                    keyboardType: TextInputType.number,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 28, letterSpacing: 8),
                    maxLength: 6,
                    decoration: const InputDecoration(labelText: 'PIN', counterText: ''),
                    validator: (v) => (v == null || v.trim().length != 6) ? '6 rəqəmli PIN daxil edin' : null,
                    enabled: !_connecting,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _nameController,
                    decoration: const InputDecoration(labelText: 'Adınız'),
                    validator: (v) => (v == null || v.trim().isEmpty) ? 'Ad daxil edin' : null,
                    enabled: !_connecting,
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: Colors.red)),
                  ],
                  const SizedBox(height: 20),
                  FilledButton(
                    onPressed: _connecting ? null : _submit,
                    child: _connecting
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Qoşul'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
