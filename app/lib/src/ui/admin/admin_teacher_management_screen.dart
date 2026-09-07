import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/admin_client.dart';
import '../../data/api_exception.dart';
import '../../models/user.dart';

/// Admin-in başqa bir istifadəçini e-poçtla müəllim edib/etməkdən çıxarması
/// (bax Çox-müəllimli idarəetmə, Faza 4) — yalnız `isAdmin` istifadəçilər
/// bu ekrana çıxış alır (bax `chat_list_screen.dart`/`host_setup_screen.dart`).
class AdminTeacherManagementScreen extends StatefulWidget {
  const AdminTeacherManagementScreen({super.key, required this.token});

  final String token;

  @override
  State<AdminTeacherManagementScreen> createState() => _AdminTeacherManagementScreenState();
}

class _AdminTeacherManagementScreenState extends State<AdminTeacherManagementScreen> {
  final _client = AdminClient(baseUrl: kApiBaseUrl);
  final _emailController = TextEditingController();

  bool _submitting = false;
  String? _error;
  UserInfo? _result;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  Future<void> _submit(bool isTeacher) async {
    final email = _emailController.text.trim();
    if (email.isEmpty) return;
    setState(() {
      _submitting = true;
      _error = null;
      _result = null;
    });
    try {
      final updated = await _client.setTeacherRole(widget.token, email: email, isTeacher: isTeacher);
      if (!mounted) return;
      setState(() => _result = updated);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Müəllim idarəetməsi')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _emailController,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'İstifadəçinin e-poçtu'),
              enabled: !_submitting,
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: FilledButton(
                    onPressed: _submitting ? null : () => _submit(true),
                    child: const Text('Müəllim et'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton(
                    onPressed: _submitting ? null : () => _submit(false),
                    child: const Text('Müəllimlikdən çıxar'),
                  ),
                ),
              ],
            ),
            if (_submitting) ...[
              const SizedBox(height: 24),
              const Center(child: CircularProgressIndicator()),
            ],
            if (_error != null) ...[
              const SizedBox(height: 16),
              Text(_error!, style: const TextStyle(color: Colors.red)),
            ],
            if (_result != null) ...[
              const SizedBox(height: 16),
              Text(
                '${_result!.displayName} (${_result!.email}) — '
                '${_result!.isTeacher ? "indi müəllimdir" : "artıq müəllim deyil"}.',
                style: const TextStyle(color: Colors.green),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
