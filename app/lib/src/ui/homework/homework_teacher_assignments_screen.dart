import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/chat_client.dart';
import '../../data/homework_client.dart';
import '../../data/live_client.dart';
import '../../models/chat.dart';
import '../../models/homework.dart';
import '../../models/question_set.dart';
import 'homework_teacher_report_screen.dart';

class _AssignmentRow {
  const _AssignmentRow({required this.assignment, required this.questionSet});
  final HomeworkAssignmentInfo assignment;
  final QuestionSetInfo? questionSet;
}

/// Müəllimin öz yaratdığı tapşırıqların siyahısı — çat seç, o çatdakı
/// tapşırıqları gör, tamamlanma sayını izlə, hesabata bax (bax Ev
/// Təkrarı Rejimi dizayn sənədi, "Hesabat YALNIZ veb-də").
class HomeworkTeacherAssignmentsScreen extends StatefulWidget {
  const HomeworkTeacherAssignmentsScreen({super.key, required this.token});

  final String token;

  @override
  State<HomeworkTeacherAssignmentsScreen> createState() => _HomeworkTeacherAssignmentsScreenState();
}

class _HomeworkTeacherAssignmentsScreenState extends State<HomeworkTeacherAssignmentsScreen> {
  final _chatClient = ChatClient(baseUrl: kApiBaseUrl);
  final _homeworkClient = HomeworkClient(baseUrl: kApiBaseUrl);
  final _liveClient = LiveClient(baseUrl: kApiBaseUrl);

  bool _loadingChats = true;
  List<ChatInfo> _chats = [];
  ChatInfo? _selectedChat;
  String? _chatsError;

  bool _loadingAssignments = false;
  List<_AssignmentRow> _rows = [];
  String? _assignmentsError;

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
      if (_selectedChat != null) _loadAssignments();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _chatsError = e.message;
        _loadingChats = false;
      });
    }
  }

  Future<void> _loadAssignments() async {
    final chat = _selectedChat;
    if (chat == null) return;
    setState(() {
      _loadingAssignments = true;
      _assignmentsError = null;
    });
    try {
      final assignments = await _homeworkClient.listAssignments(widget.token, chatId: chat.id);
      final rows = <_AssignmentRow>[];
      for (final a in assignments) {
        QuestionSetInfo? qs;
        try {
          qs = await _liveClient.getQuestionSet(widget.token, a.questionSetId);
        } on ApiException {
          qs = null;
        }
        rows.add(_AssignmentRow(assignment: a, questionSet: qs));
      }
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loadingAssignments = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _assignmentsError = e.message;
        _loadingAssignments = false;
      });
    }
  }

  void _selectChat(ChatInfo? chat) {
    if (chat == null) return;
    setState(() => _selectedChat = chat);
    _loadAssignments();
  }

  void _openReport(_AssignmentRow row) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => HomeworkTeacherReportScreen(token: widget.token, assignmentId: row.assignment.id),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Tapşırıq hesabatları')),
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
        Expanded(child: _buildAssignmentsList()),
      ],
    );
  }

  Widget _buildAssignmentsList() {
    if (_loadingAssignments) return const Center(child: CircularProgressIndicator());
    if (_assignmentsError != null) return Center(child: Text(_assignmentsError!));
    if (_rows.isEmpty) {
      return const Center(child: Text('Bu çat üçün hələ tapşırıq təyin edilməyib.'));
    }
    return ListView.separated(
      itemCount: _rows.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final row = _rows[index];
        final qs = row.questionSet;
        return ListTile(
          leading: CircleAvatar(child: Text(row.assignment.completedCount.toString())),
          title: Text(qs != null ? '${qs.subjectLabel} — ${qs.title}' : 'Sual bankı #${row.assignment.questionSetId}'),
          subtitle: Text(
            'Son tarix: ${row.assignment.dueDate} · Tamamlayan: '
            '${row.assignment.completedCount}/${row.assignment.totalMembers}',
          ),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => _openReport(row),
        );
      },
    );
  }
}
