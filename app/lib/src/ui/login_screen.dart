import 'package:flutter/material.dart';

import '../config.dart';
import '../data/api_exception.dart';
import '../data/auth_client.dart';
import '../data/session_storage.dart';
import 'chat_list_screen.dart';
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
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => ChatListScreen(
          token: auth.token,
          userId: auth.user.id,
          displayName: auth.user.displayName,
          sessionStorage: widget.sessionStorage,
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
