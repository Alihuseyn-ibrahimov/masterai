import 'dart:async';

import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/live_client.dart';
import '../../data/session_storage.dart';
import '../../models/question_set.dart';
import '../login_screen.dart';
import 'host_session_screen.dart';

/// Host konsolunun ilk ekranı — fənn seç, mövcud sual bankından seç
/// (ya yeni link əlavə et), sonra canlı sessiya başlat. Bax dizayn
/// sənədi, "Frontend — iki yeni ekran ailəsi", A/Ekran 1.
class HostSetupScreen extends StatefulWidget {
  const HostSetupScreen({super.key, required this.token, required this.sessionStorage});

  final String token;
  final SessionStorage sessionStorage;

  @override
  State<HostSetupScreen> createState() => _HostSetupScreenState();
}

class _HostSetupScreenState extends State<HostSetupScreen> {
  final _liveClient = LiveClient(baseUrl: kApiBaseUrl);
  Timer? _pollTimer;

  bool _loading = true;
  List<QuestionSetInfo>? _questionSets;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  /// "processing" statuslu sual bankı qalarkən 2 saniyədə bir arxa-fonda
  /// özü yenilənir (bax dizayn sənədi, "Material emalı statusu") — əl
  /// ilə "Yenilə" düyməsi hələ də mövcuddur. `_loading` yalnız İLK
  /// yükləmədə true olur ki, poll zamanı siyahı spinner-lə "titrəməsin".
  Future<void> _load() async {
    _pollTimer?.cancel();
    try {
      final sets = await _liveClient.listQuestionSets(widget.token);
      if (!mounted) return;
      setState(() {
        _questionSets = sets;
        _error = null;
        _loading = false;
      });
      if (sets.any((qs) => qs.status == 'processing')) {
        _pollTimer = Timer(const Duration(seconds: 2), _load);
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  void _refresh() => _load();

  Future<void> _logout() async {
    await widget.sessionStorage.clear();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => LoginScreen(sessionStorage: widget.sessionStorage)),
      (route) => false,
    );
  }

  Future<void> _createQuestionSet() async {
    String subject = kSubjectLabels.keys.first;
    final titleController = TextEditingController();
    final locationController = TextEditingController();

    final created = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Yeni sual bankı'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DropdownButtonFormField<String>(
                initialValue: subject,
                decoration: const InputDecoration(labelText: 'Fənn'),
                items: kSubjectLabels.entries
                    .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                    .toList(),
                onChanged: (v) => setDialogState(() => subject = v ?? subject),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: titleController,
                decoration: const InputDecoration(labelText: 'Başlıq (məs. "3-cü fəsil")'),
                autofocus: true,
              ),
              const SizedBox(height: 8),
              TextField(
                controller: locationController,
                decoration: const InputDecoration(labelText: 'Material linki (sayt ünvanı)'),
                keyboardType: TextInputType.url,
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Ləğv et')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Yarat')),
          ],
        ),
      ),
    );
    if (created != true) return;
    if (titleController.text.trim().isEmpty || locationController.text.trim().isEmpty) return;

    try {
      await _liveClient.createQuestionSet(
        widget.token,
        subject: subject,
        title: titleController.text.trim(),
        location: locationController.text.trim(),
      );
      _refresh();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _startSession(QuestionSetInfo qs) async {
    try {
      final session = await _liveClient.createLiveSession(widget.token, qs.id);
      if (!mounted) return;
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => HostSessionScreen(token: widget.token, session: session, questionSet: qs),
      ));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('MasterAI — Müəllim konsolu'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh, tooltip: 'Yenilə'),
          IconButton(icon: const Icon(Icons.logout), onPressed: _logout, tooltip: 'Çıxış'),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _createQuestionSet,
        icon: const Icon(Icons.add),
        label: const Text('Yeni sual bankı'),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(child: Text(_error!));
    }
    final questionSets = _questionSets!;
    if (questionSets.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Hələ heç bir sual bankı yoxdur. Aşağıdakı düymə ilə fənn seçib material linki əlavə edin.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    return ListView.separated(
      itemCount: questionSets.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final qs = questionSets[index];
        return ListTile(
          leading: CircleAvatar(child: Text(qs.questionCount.toString())),
          title: Text(qs.title),
          subtitle: Text('${qs.subjectLabel} — ${_statusLabel(qs.status, qs.error)}'),
          trailing: qs.status == 'ready'
              ? FilledButton(
                  onPressed: () => _startSession(qs),
                  child: const Text('Sessiya başlat'),
                )
              : null,
        );
      },
    );
  }

  String _statusLabel(String status, String? error) {
    switch (status) {
      case 'processing':
        return 'Hazırlanır…';
      case 'ready':
        return 'Hazırdır';
      case 'failed':
        return 'Uğursuz oldu${error != null ? ': $error' : ''}';
      default:
        return status;
    }
  }
}
