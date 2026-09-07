import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import 'src/data/session_storage.dart';
import 'src/ui/chat_list_screen.dart';
import 'src/ui/host/host_setup_screen.dart';
import 'src/ui/login_screen.dart';

void main() {
  runApp(const MasterAiApp());
}

class MasterAiApp extends StatelessWidget {
  const MasterAiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MasterAI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2F6FED)),
        useMaterial3: true,
      ),
      home: const _Bootstrap(),
    );
  }
}

/// Açılışda saxlanmış sessiyanı yoxlayır — token yığılıbsa birbaşa çat
/// siyahısına, yoxdursa giriş ekranına yönləndirir. Backend-də `/auth/me`
/// olmadığı üçün token-in ÖZÜ doğrulanmır (bax `session_storage.dart`
/// qeydi) — `ChatListScreen` ilk `GET /chats` çağırışında `401` alsa
/// özü logout edəcək.
class _Bootstrap extends StatefulWidget {
  const _Bootstrap();

  @override
  State<_Bootstrap> createState() => _BootstrapState();
}

class _BootstrapState extends State<_Bootstrap> {
  final SessionStorage _sessionStorage = SecureSessionStorage();
  bool _checking = true;
  String? _token;
  int? _userId;
  String? _displayName;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final token = await _sessionStorage.readToken();
    final userId = await _sessionStorage.readUserId();
    final displayName = await _sessionStorage.readDisplayName();
    if (!mounted) return;
    setState(() {
      _token = token;
      _userId = userId;
      _displayName = displayName;
      _checking = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_checking) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_token != null && _userId != null && _displayName != null) {
      // Veb build YALNIZ müəllim host konsolu üçündür (bax dizayn sənədi,
      // "Frontend"), mobil app tələbə axınıdır — platformlar arasında
      // ayrı ekran ailəsi.
      if (kIsWeb) {
        return HostSetupScreen(token: _token!, sessionStorage: _sessionStorage);
      }
      return ChatListScreen(
        token: _token!,
        userId: _userId!,
        displayName: _displayName!,
        sessionStorage: _sessionStorage,
      );
    }
    return LoginScreen(sessionStorage: _sessionStorage);
  }
}
