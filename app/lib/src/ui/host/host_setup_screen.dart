import 'dart:async';

import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/chat_client.dart';
import '../../data/homework_client.dart';
import '../../data/live_client.dart';
import '../../data/session_storage.dart';
import '../../models/chat.dart';
import '../../models/question_set.dart';
import '../login_screen.dart';
import 'host_session_screen.dart';

/// Host konsolunun ilk ekranı — fənn seç, mövcud sual bankından seç
/// (ya yeni link əlavə et), sonra canlı sessiya başlat. Bax dizayn
/// sənədi, "Frontend — iki yeni ekran ailəsi", A/Ekran 1.
///
/// `isTeacher=true` olanda hər "Hazırdır" bank üçün "Tapşırıq kimi təyin
/// et" düyməsi də görünür (bax Ev Təkrarı Rejimi dizayn sənədi).
class HostSetupScreen extends StatefulWidget {
  const HostSetupScreen({
    super.key,
    required this.token,
    required this.sessionStorage,
    required this.isTeacher,
  });

  final String token;
  final SessionStorage sessionStorage;
  final bool isTeacher;

  @override
  State<HostSetupScreen> createState() => _HostSetupScreenState();
}

class _HostSetupScreenState extends State<HostSetupScreen> {
  final _liveClient = LiveClient(baseUrl: kApiBaseUrl);
  final _chatClient = ChatClient(baseUrl: kApiBaseUrl);
  final _homeworkClient = HomeworkClient(baseUrl: kApiBaseUrl);
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

  String _isoDate(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  /// Sual bankını mövcud bir qrup çatına ev tapşırığı kimi təyin edir
  /// (bax Ev Təkrarı Rejimi dizayn sənədi — bu ekrandan çat seçimi
  /// tələb olunur, çünki bank hələ hansısa çata bağlı deyil).
  Future<void> _assignHomework(QuestionSetInfo qs) async {
    List<ChatInfo> chats;
    try {
      chats = await _chatClient.listChats(widget.token);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      return;
    }
    if (!mounted) return;
    if (chats.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Tapşırıq təyin etmək üçün əvvəlcə bir qrup çatı olmalıdır.')),
      );
      return;
    }

    ChatInfo selectedChat = chats.first;
    DateTime selectedDate = DateTime.now().add(const Duration(days: 7));

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('"${qs.title}" — tapşırıq kimi təyin et'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DropdownButtonFormField<ChatInfo>(
                initialValue: selectedChat,
                decoration: const InputDecoration(labelText: 'Qrup çatı'),
                items: chats
                    .map((c) => DropdownMenuItem(value: c, child: Text(c.name ?? 'Şəxsi çat')))
                    .toList(),
                onChanged: (v) => setDialogState(() => selectedChat = v ?? selectedChat),
              ),
              const SizedBox(height: 12),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Son tarix'),
                subtitle: Text(_isoDate(selectedDate)),
                trailing: const Icon(Icons.calendar_month),
                onTap: () async {
                  final picked = await showDatePicker(
                    context: context,
                    initialDate: selectedDate,
                    firstDate: DateTime.now(),
                    lastDate: DateTime.now().add(const Duration(days: 365)),
                  );
                  if (picked != null) setDialogState(() => selectedDate = picked);
                },
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Ləğv et')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Təyin et')),
          ],
        ),
      ),
    );
    if (confirmed != true) return;

    try {
      await _homeworkClient.createAssignment(
        widget.token,
        chatId: selectedChat.id,
        questionSetId: qs.id,
        dueDate: _isoDate(selectedDate),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Tapşırıq təyin olundu.')));
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
              ? Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (widget.isTeacher)
                      IconButton(
                        icon: const Icon(Icons.assignment_add),
                        tooltip: 'Tapşırıq kimi təyin et',
                        onPressed: () => _assignHomework(qs),
                      ),
                    FilledButton(
                      onPressed: () => _startSession(qs),
                      child: const Text('Sessiya başlat'),
                    ),
                  ],
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
