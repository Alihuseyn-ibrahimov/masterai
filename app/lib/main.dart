import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'src/data/session_storage.dart';
import 'src/ui/chat_list_screen.dart';
import 'src/ui/host/host_setup_screen.dart';
import 'src/ui/login_screen.dart';

void main() {
  runApp(const MasterAiApp());
}

/// Başlıqlar üçün Nunito (dəyirmi, canlı), mətn üçün Inter (oxunaqlı) —
/// bax vizual dizayn yenilənməsi speci. `fontFamilyFallback` TƏHLÜKƏSİZLİK
/// ŞƏBƏKƏSİDİR: seçilmiş fontda olmayan hər hansı hərf (Azərbaycan Ə/ə
/// riski, bax `findings.md`) avtomatik defolt Roboto-ya keçir — heç bir
/// hərf "boş qutu" kimi göstərilmir.
const _fontFallback = ['Roboto'];

TextTheme _buildTextTheme(TextTheme base) {
  final body = GoogleFonts.interTextTheme(base);
  TextStyle heading(TextStyle? style, FontWeight weight) => GoogleFonts.nunito(
        textStyle: style,
        fontWeight: weight,
        fontFamilyFallback: _fontFallback,
      );
  return body.copyWith(
    displayLarge: heading(body.displayLarge, FontWeight.w800),
    displayMedium: heading(body.displayMedium, FontWeight.w800),
    displaySmall: heading(body.displaySmall, FontWeight.w700),
    headlineLarge: heading(body.headlineLarge, FontWeight.w700),
    headlineMedium: heading(body.headlineMedium, FontWeight.w700),
    headlineSmall: heading(body.headlineSmall, FontWeight.w700),
    titleLarge: heading(body.titleLarge, FontWeight.w700),
  );
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
        textTheme: _buildTextTheme(ThemeData().textTheme),
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
  bool _isTeacher = false;
  bool _isAdmin = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final token = await _sessionStorage.readToken();
    final userId = await _sessionStorage.readUserId();
    final displayName = await _sessionStorage.readDisplayName();
    final isTeacher = await _sessionStorage.readIsTeacher();
    final isAdmin = await _sessionStorage.readIsAdmin();
    if (!mounted) return;
    setState(() {
      _token = token;
      _userId = userId;
      _displayName = displayName;
      _isTeacher = isTeacher;
      _isAdmin = isAdmin;
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
        return HostSetupScreen(
          token: _token!,
          sessionStorage: _sessionStorage,
          isTeacher: _isTeacher,
          isAdmin: _isAdmin,
        );
      }
      return ChatListScreen(
        token: _token!,
        userId: _userId!,
        displayName: _displayName!,
        sessionStorage: _sessionStorage,
        isTeacher: _isTeacher,
        isAdmin: _isAdmin,
      );
    }
    return LoginScreen(sessionStorage: _sessionStorage);
  }
}
