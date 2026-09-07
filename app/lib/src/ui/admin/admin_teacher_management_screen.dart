import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/admin_client.dart';
import '../../data/api_exception.dart';
import '../../models/user.dart';

/// Admin-in başqa bir istifadəçini e-poçtla müəllim edib/etməkdən çıxarması
/// VƏ hazırkı müəllim siyahısına baxması (bax Çox-müəllimli idarəetmə,
/// Faza 4) — yalnız `isAdmin` istifadəçilər bu ekrana çıxış alır (bax
/// `chat_list_screen.dart`/`host_setup_screen.dart`).
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
  late Future<List<UserInfo>> _teachersFuture;

  @override
  void initState() {
    super.initState();
    _teachersFuture = _client.listTeachers(widget.token);
  }

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  void _refreshTeachers() => setState(() => _teachersFuture = _client.listTeachers(widget.token));

  Future<void> _submit(String email, bool isTeacher) async {
    if (email.isEmpty) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await _client.setTeacherRole(widget.token, email: email, isTeacher: isTeacher);
      if (!mounted) return;
      _refreshTeachers();
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
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
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
                        onPressed: _submitting ? null : () => _submit(_emailController.text.trim(), true),
                        child: const Text('Müəllim et'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: _submitting ? null : () => _submit(_emailController.text.trim(), false),
                        child: const Text('Müəllimlikdən çıxar'),
                      ),
                    ),
                  ],
                ),
                if (_submitting) ...[
                  const SizedBox(height: 16),
                  const Center(child: CircularProgressIndicator()),
                ],
                if (_error != null) ...[
                  const SizedBox(height: 16),
                  Text(_error!, style: const TextStyle(color: Colors.red)),
                ],
              ],
            ),
          ),
          const Divider(height: 1),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text('Hazırkı müəllimlər', style: TextStyle(fontWeight: FontWeight.bold)),
            ),
          ),
          Expanded(child: _buildTeachersList()),
        ],
      ),
    );
  }

  Widget _buildTeachersList() {
    return FutureBuilder<List<UserInfo>>(
      future: _teachersFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          final message =
              snapshot.error is ApiException ? (snapshot.error as ApiException).message : 'Xəta baş verdi';
          return Center(child: Text(message));
        }
        final teachers = snapshot.data!;
        if (teachers.isEmpty) {
          return const Center(child: Text('Hələ heç bir müəllim yoxdur.'));
        }
        return ListView.separated(
          itemCount: teachers.length,
          separatorBuilder: (_, _) => const Divider(height: 1),
          itemBuilder: (context, index) {
            final t = teachers[index];
            return ListTile(
              leading: const CircleAvatar(child: Icon(Icons.school)),
              title: Text(t.displayName),
              subtitle: Text(t.email),
              trailing: IconButton(
                icon: const Icon(Icons.remove_circle_outline),
                tooltip: 'Müəllimlikdən çıxar',
                onPressed: _submitting ? null : () => _submit(t.email, false),
              ),
            );
          },
        );
      },
    );
  }
}
