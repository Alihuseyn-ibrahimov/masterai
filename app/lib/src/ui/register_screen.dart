import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../config.dart';
import '../data/api_exception.dart';
import '../data/auth_client.dart';
import '../data/session_storage.dart';
import 'chat_list_screen.dart';
import 'host/host_setup_screen.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key, required this.sessionStorage});

  final SessionStorage sessionStorage;

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _authClient = AuthClient(baseUrl: kApiBaseUrl);

  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _nameController.dispose();
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
      final auth = await _authClient.register(
        email: _emailController.text.trim(),
        password: _passwordController.text,
        displayName: _nameController.text.trim(),
      );
      await widget.sessionStorage.writeSession(
        token: auth.token,
        userId: auth.user.id,
        displayName: auth.user.displayName,
        isTeacher: auth.user.isTeacher,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => kIsWeb
            ? HostSetupScreen(
                token: auth.token,
                sessionStorage: widget.sessionStorage,
                isTeacher: auth.user.isTeacher,
              )
            : ChatListScreen(
                token: auth.token,
                userId: auth.user.id,
                displayName: auth.user.displayName,
                sessionStorage: widget.sessionStorage,
                isTeacher: auth.user.isTeacher,
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
      appBar: AppBar(title: const Text('Qeydiyyat')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextFormField(
                  controller: _nameController,
                  decoration: const InputDecoration(labelText: 'Ad Soyad'),
                  validator: (v) => (v == null || v.trim().isEmpty) ? 'Ad daxil edin' : null,
                ),
                const SizedBox(height: 12),
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
                  decoration: const InputDecoration(labelText: 'Şifrə (min. 8 simvol)'),
                  validator: (v) =>
                      (v == null || v.length < 8) ? 'Şifrə ən azı 8 simvol olmalıdır' : null,
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
                      : const Text('Qeydiyyatdan keç'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
