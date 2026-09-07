import 'package:flutter/material.dart';

import '../config.dart';
import '../data/api_exception.dart';
import '../data/chat_client.dart';
import '../data/session_storage.dart';
import '../models/chat.dart';
import 'chat_screen.dart';
import 'homework/homework_assignment_list_screen.dart';
import 'login_screen.dart';

class ChatListScreen extends StatefulWidget {
  const ChatListScreen({
    super.key,
    required this.token,
    required this.userId,
    required this.displayName,
    required this.sessionStorage,
    required this.isTeacher,
  });

  final String token;
  final int userId;
  final String displayName;
  final SessionStorage sessionStorage;
  final bool isTeacher;

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
            icon: const Icon(Icons.assignment),
            tooltip: 'Tapşırıqlarım',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => HomeworkAssignmentListScreen(token: widget.token),
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
                subtitle: Text(chat.kind == 'group' ? 'Qrup çatı' : 'Şəxsi çat'),
                onTap: () => _openChat(chat),
              );
            },
          );
        },
      ),
    );
  }
}
