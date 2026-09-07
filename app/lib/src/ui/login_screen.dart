import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../config.dart';
import '../data/api_exception.dart';
import '../data/auth_client.dart';
import '../data/session_storage.dart';
import 'chat_list_screen.dart';
import 'host/host_setup_screen.dart';
import 'join/join_pin_screen.dart';
import 'register_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.sessionStorage});

  final SessionStorage sessionStorage;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _authClient = AuthClient(baseUrl: kApiBaseUrl);

  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final auth = await _authClient.login(
        email: _emailController.text.trim(),
        password: _passwordController.text,
      );
      await widget.sessionStorage.writeSession(
        token: auth.token,
        userId: auth.user.id,
        displayName: auth.user.displayName,
        isTeacher: auth.user.isTeacher,
        isAdmin: auth.user.isAdmin,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => kIsWeb
            ? HostSetupScreen(
                token: auth.token,
                sessionStorage: widget.sessionStorage,
                isTeacher: auth.user.isTeacher,
                isAdmin: auth.user.isAdmin,
              )
            : ChatListScreen(
                token: auth.token,
                userId: auth.user.id,
                displayName: auth.user.displayName,
                sessionStorage: widget.sessionStorage,
                isTeacher: auth.user.isTeacher,
                isAdmin: auth.user.isAdmin,
              ),
      ));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
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
                  const Icon(Icons.school, size: 64, color: Color(0xFF2F6FED)),
                  const SizedBox(height: 12),
                  Text(
                    'MasterAI',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                  const SizedBox(height: 24),
                  // Hesab tələb etməyən giriş nöqtəsi (bax dizayn sənədi,
                  // "Tələbə tərəfi") — login formasından ƏVVƏL göstərilir.
                  OutlinedButton.icon(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const JoinPinScreen()),
                    ),
                    icon: const Icon(Icons.groups),
                    label: const Text('Sinif sessiyasına qoşul (PIN ilə)'),
                  ),
                  const SizedBox(height: 20),
                  const Row(
                    children: [
                      Expanded(child: Divider()),
                      Padding(padding: EdgeInsets.symmetric(horizontal: 12), child: Text('və ya')),
                      Expanded(child: Divider()),
                    ],
                  ),
                  const SizedBox(height: 20),
                  TextFormField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(labelText: 'E-poçt'),
                    validator: (v) => (v == null || v.trim().isEmpty) ? 'E-poçt daxil edin' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _passwordController,
                    obscureText: true,
                    decoration: const InputDecoration(labelText: 'Şifrə'),
                    validator: (v) => (v == null || v.isEmpty) ? 'Şifrə daxil edin' : null,
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: Colors.red)),
                  ],
                  const SizedBox(height: 20),
                  FilledButton(
                    onPressed: _submitting ? null : _submit,
                    child: _submitting
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Daxil ol'),
                  ),
                  const SizedBox(height: 8),
                  TextButton(
                    onPressed: _submitting
                        ? null
                        : () => Navigator.of(context).push(MaterialPageRoute(
                              builder: (_) => RegisterScreen(sessionStorage: widget.sessionStorage),
                            )),
                    child: const Text('Hesabınız yoxdur? Qeydiyyatdan keçin'),
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
