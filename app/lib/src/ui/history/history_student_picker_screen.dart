import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/chat_client.dart';
import '../../models/chat.dart';
import 'student_history_screen.dart';

/// Müəllimin "Fərdi tələbə tarixçəsi" giriş nöqtəsi — əvvəlcə çat seç,
/// sonra o çatın üzvlərindən birini seç (bax `student_history_screen.dart`).
class HistoryStudentPickerScreen extends StatefulWidget {
  const HistoryStudentPickerScreen({super.key, required this.token});

  final String token;

  @override
  State<HistoryStudentPickerScreen> createState() => _HistoryStudentPickerScreenState();
}

class _HistoryStudentPickerScreenState extends State<HistoryStudentPickerScreen> {
  final _chatClient = ChatClient(baseUrl: kApiBaseUrl);

  bool _loadingChats = true;
  List<ChatInfo> _chats = [];
  ChatInfo? _selectedChat;
  String? _chatsError;

  bool _loadingMembers = false;
  List<ChatMemberInfo> _members = [];
  String? _membersError;

  @override
  void initState() {
    super.initState();
    _loadChats();
  }

  Future<void> _loadChats() async {
    try {
      final chats = await _chatClient.listChats(widget.token);
      if (!mounted) return;
      setState(() {
        _chats = chats;
        _selectedChat = chats.isNotEmpty ? chats.first : null;
        _loadingChats = false;
      });
      if (_selectedChat != null) _loadMembers();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _chatsError = e.message;
        _loadingChats = false;
      });
    }
  }

  Future<void> _loadMembers() async {
    final chat = _selectedChat;
    if (chat == null) return;
    setState(() {
      _loadingMembers = true;
      _membersError = null;
    });
    try {
      final members = await _chatClient.listMembers(widget.token, chat.id);
      if (!mounted) return;
      setState(() {
        _members = members;
        _loadingMembers = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _membersError = e.message;
        _loadingMembers = false;
      });
    }
  }

  void _selectChat(ChatInfo? chat) {
    if (chat == null) return;
    setState(() => _selectedChat = chat);
    _loadMembers();
  }

  void _openStudent(ChatMemberInfo member) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => StudentHistoryScreen(
        token: widget.token,
        studentId: member.userId,
        displayName: member.displayName,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Fərdi tələbə tarixçəsi')),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loadingChats) return const Center(child: CircularProgressIndicator());
    if (_chatsError != null) return Center(child: Text(_chatsError!));
    if (_chats.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Hələ heç bir çatınız yoxdur.', textAlign: TextAlign.center),
        ),
      );
    }
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: DropdownButtonFormField<ChatInfo>(
            initialValue: _selectedChat,
            decoration: const InputDecoration(labelText: 'Çat'),
            items: _chats
                .map((c) => DropdownMenuItem(value: c, child: Text('${c.name ?? 'Şəxsi çat'} (ID: ${c.id})')))
                .toList(),
            onChanged: _selectChat,
          ),
        ),
        Expanded(child: _buildMembersList()),
      ],
    );
  }

  Widget _buildMembersList() {
    if (_loadingMembers) return const Center(child: CircularProgressIndicator());
    if (_membersError != null) return Center(child: Text(_membersError!));
    if (_members.isEmpty) {
      return const Center(child: Text('Bu çatda üzv yoxdur.'));
    }
    return ListView.separated(
      itemCount: _members.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final member = _members[index];
        return ListTile(
          leading: const CircleAvatar(child: Icon(Icons.person)),
          title: Text(member.displayName),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => _openStudent(member),
        );
      },
    );
  }
}
