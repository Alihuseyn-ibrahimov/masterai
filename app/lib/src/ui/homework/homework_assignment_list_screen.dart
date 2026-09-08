import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/homework_client.dart';
import '../../models/homework.dart';
import '../../theme/app_subject_colors.dart';
import 'homework_solve_screen.dart';

/// Tələbənin bütün çatlarındakı ev tapşırıqları — bax Ev Təkrarı Rejimi
/// dizayn sənədi, "Tapşırıqlarım ekranı".
class HomeworkAssignmentListScreen extends StatefulWidget {
  const HomeworkAssignmentListScreen({super.key, required this.token});

  final String token;

  @override
  State<HomeworkAssignmentListScreen> createState() => _HomeworkAssignmentListScreenState();
}

class _HomeworkAssignmentListScreenState extends State<HomeworkAssignmentListScreen> {
  final _client = HomeworkClient(baseUrl: kApiBaseUrl);
  late Future<List<MyAssignmentInfo>> _future;

  @override
  void initState() {
    super.initState();
    _future = _client.listMyAssignments(widget.token);
  }

  void _refresh() => setState(() => _future = _client.listMyAssignments(widget.token));

  bool _isOverdue(MyAssignmentInfo a) {
    if (a.status == 'tamamlanıb') return false;
    final due = DateTime.tryParse(a.dueDate);
    if (due == null) return false;
    final today = DateTime.now();
    return due.isBefore(DateTime(today.year, today.month, today.day));
  }

  Future<void> _open(MyAssignmentInfo assignment) async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => HomeworkSolveScreen(token: widget.token, assignment: assignment),
    ));
    _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tapşırıqlarım'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh, tooltip: 'Yenilə')],
      ),
      body: FutureBuilder<List<MyAssignmentInfo>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            final message =
                snapshot.error is ApiException ? (snapshot.error as ApiException).message : 'Xəta baş verdi';
            return Center(child: Text(message));
          }
          final assignments = snapshot.data!;
          if (assignments.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text('Hələ sizə tapşırıq təyin edilməyib.', textAlign: TextAlign.center),
              ),
            );
          }
          return ListView.separated(
            itemCount: assignments.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (context, index) {
              final a = assignments[index];
              final overdue = _isOverdue(a);
              return ListTile(
                leading: CircleAvatar(
                  backgroundColor:
                      a.status == 'tamamlanıb' ? Colors.green : subjectColor(context, a.subject),
                  foregroundColor: a.status == 'tamamlanıb' ? Colors.white : subjectColorForeground(context),
                  child: Icon(a.status == 'tamamlanıb' ? Icons.check : Icons.assignment),
                ),
                title: Text('${a.subjectLabel} — ${a.title}'),
                subtitle: Text(
                  '${_statusLabel(a.status, a.score)} · Son tarix: ${a.dueDate}${overdue ? ' (gecikmiş)' : ''}',
                  style: overdue ? const TextStyle(color: Colors.red) : null,
                ),
                onTap: () => _open(a),
              );
            },
          );
        },
      ),
    );
  }

  String _statusLabel(String status, int? score) => switch (status) {
        'tamamlanıb' => 'Tamamlanıb — $score xal',
        'davam edir' => 'Davam edir',
        _ => 'Gözləyir',
      };
}
