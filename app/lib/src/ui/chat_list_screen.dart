import 'package:flutter/material.dart';

import '../config.dart';
import '../data/api_exception.dart';
import '../data/chat_client.dart';
import '../data/session_storage.dart';
import '../models/chat.dart';
import 'admin/admin_teacher_management_screen.dart';
import 'chat_screen.dart';
import 'history/my_history_screen.dart';
import 'homework/homework_assignment_list_screen.dart';
import 'join/join_pin_screen.dart';
import 'login_screen.dart';

class ChatListScreen extends StatefulWidget {
  const ChatListScreen({
    super.key,
    required this.token,
    required this.userId,
    required this.displayName,
    required this.sessionStorage,
    required this.isTeacher,
    required this.isAdmin,
  });

  final String token;
  final int userId;
  final String displayName;
  final SessionStorage sessionStorage;
  final bool isTeacher;
  final bool isAdmin;

  @override
  State<ChatListScreen> createState() => _ChatListScreenState();
}

class _ChatListScreenState extends State<ChatListScreen> {
  final _chatClient = ChatClient(baseUrl: kApiBaseUrl);
  late Future<List<ChatInfo>> _chatsFuture;

  @override
  void initState() {
    super.initState();
    _chatsFuture = _load();
  }

  Future<List<ChatInfo>> _load() async {
    try {
      return await _chatClient.listChats(widget.token);
    } on ApiException catch (e) {
      if (e.statusCode == 401) {
        await _logout();
      }
      rethrow;
    }
  }

  Future<void> _logout() async {
    await widget.sessionStorage.clear();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => LoginScreen(sessionStorage: widget.sessionStorage)),
      (route) => false,
    );
  }

  Future<void> _createGroupChat() async {
    final nameController = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Yeni qrup çatı'),
        content: TextField(
          controller: nameController,
          decoration: const InputDecoration(labelText: 'Qrup adı'),
          autofocus: true,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Ləğv et')),
          FilledButton(
            onPressed: () => Navigator.pop(context, nameController.text.trim()),
            child: const Text('Yarat'),
          ),
        ],
      ),
    );
    if (name == null || name.isEmpty) return;

    try {
      final chat = await _chatClient.createGroupChat(widget.token, name: name);
      setState(() => _chatsFuture = _load());
      if (!mounted) return;
      _openChat(chat);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  /// Mövcud bir qrup çatına özü-özünə qoşulur — müəllim çat ID-sini
  /// (host konsolunda/çat siyahısında görünən rəqəm) tələbələrə ayrıca
  /// bildirir, bax `masterai/CLAUDE.md`, "Ev Təkrarı Rejimi" bölməsi.
  Future<void> _joinChat() async {
    final idController = TextEditingController();
    final chatId = await showDialog<int>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Çata qoşul'),
        content: TextField(
          controller: idController,
          decoration: const InputDecoration(labelText: 'Çat ID (müəllimdən alın)'),
          keyboardType: TextInputType.number,
          autofocus: true,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Ləğv et')),
          FilledButton(
            onPressed: () => Navigator.pop(context, int.tryParse(idController.text.trim())),
            child: const Text('Qoşul'),
          ),
        ],
      ),
    );
    if (chatId == null) return;

    try {
      final chat = await _chatClient.joinChat(widget.token, chatId);
      setState(() => _chatsFuture = _load());
      if (!mounted) return;
      _openChat(chat);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  void _openChat(ChatInfo chat) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        chat: chat,
        token: widget.token,
        userId: widget.userId,
        isTeacher: widget.isTeacher,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Salam, ${widget.displayName}'),
        actions: [
          IconButton(
            icon: const Icon(Icons.groups),
            tooltip: 'Sinif sessiyasına qoşul (PIN ilə)',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => JoinPinScreen(token: widget.token),
            )),
          ),
          IconButton(icon: const Icon(Icons.group_add), tooltip: 'Çata qoşul', onPressed: _joinChat),
          IconButton(
            icon: const Icon(Icons.assignment),
            tooltip: 'Tapşırıqlarım',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => HomeworkAssignmentListScreen(token: widget.token),
            )),
          ),
          IconButton(
            icon: const Icon(Icons.history),
            tooltip: 'Mənim tarixçəm',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => MyHistoryScreen(token: widget.token),
            )),
          ),
          if (widget.isAdmin)
            IconButton(
              icon: const Icon(Icons.admin_panel_settings),
              tooltip: 'Müəllim idarəetməsi',
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => AdminTeacherManagementScreen(token: widget.token),
              )),
            ),
          IconButton(icon: const Icon(Icons.logout), onPressed: _logout, tooltip: 'Çıxış'),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _createGroupChat,
        child: const Icon(Icons.add),
      ),
      body: FutureBuilder<List<ChatInfo>>(
        future: _chatsFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            final message =
                snapshot.error is ApiException ? (snapshot.error as ApiException).message : 'Xəta baş verdi';
            return Center(child: Text(message));
          }
          final chats = snapshot.data!;
          if (chats.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'Hələ heç bir çatınız yoxdur. Aşağıdakı + düyməsi ilə qrup çatı yaradın.',
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }
          return ListView.separated(
            itemCount: chats.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (context, index) {
              final chat = chats[index];
              return ListTile(
                leading: CircleAvatar(
                  child: Icon(chat.kind == 'group' ? Icons.groups : Icons.person),
                ),
                title: Text(chat.name ?? 'Şəxsi çat'),
                subtitle: Text(
                  chat.kind == 'group' ? 'Qrup çatı · ID: ${chat.id}' : 'Şəxsi çat',
                ),
                onTap: () => _openChat(chat),
              );
            },
          );
        },
      ),
    );
  }
}
