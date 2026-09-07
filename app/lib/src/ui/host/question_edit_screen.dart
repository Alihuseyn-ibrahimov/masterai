import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/live_client.dart';
import '../../models/live_question.dart';
import 'question_form_screen.dart';

/// Bir sual bankının suallarının siyahısı — redaktə et/sil (bax Sual
/// redaktə/təsdiq ekranı, Faza 5). Sual sayı/sırası bura daxil deyil,
/// yalnız mövcud sualların məzmunu dəyişdirilə/silinə bilər.
class QuestionEditScreen extends StatefulWidget {
  const QuestionEditScreen({super.key, required this.token, required this.questionSetId, required this.title});

  final String token;
  final int questionSetId;
  final String title;

  @override
  State<QuestionEditScreen> createState() => _QuestionEditScreenState();
}

class _QuestionEditScreenState extends State<QuestionEditScreen> {
  final _liveClient = LiveClient(baseUrl: kApiBaseUrl);
  late Future<List<LiveQuestionInfo>> _future;

  static const _letters = ['A', 'B', 'C', 'D', 'E'];

  @override
  void initState() {
    super.initState();
    _future = _liveClient.listQuestions(widget.token, widget.questionSetId);
  }

  void _refresh() => setState(() => _future = _liveClient.listQuestions(widget.token, widget.questionSetId));

  Future<void> _edit(LiveQuestionInfo question) async {
    final changed = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => QuestionFormScreen(token: widget.token, question: question),
    ));
    if (changed == true) _refresh();
  }

  Future<void> _delete(LiveQuestionInfo question) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sualı sil'),
        content: Text('"${question.question}" silinsin?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Ləğv et')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Sil')),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await _liveClient.deleteQuestion(widget.token, question.id);
      _refresh();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('${widget.title} — suallar')),
      body: FutureBuilder<List<LiveQuestionInfo>>(
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
          final questions = snapshot.data!;
          if (questions.isEmpty) {
            return const Center(child: Text('Bu sual bankında sual yoxdur.'));
          }
          return ListView.separated(
            itemCount: questions.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (context, index) {
              final q = questions[index];
              return ListTile(
                title: Text(q.question),
                subtitle: Text('Düzgün cavab: ${_letters[q.correctIndex]}) ${q.options[q.correctIndex]}'),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(icon: const Icon(Icons.edit), tooltip: 'Redaktə et', onPressed: () => _edit(q)),
                    IconButton(icon: const Icon(Icons.delete_outline), tooltip: 'Sil', onPressed: () => _delete(q)),
                  ],
                ),
              );
            },
          );
        },
      ),
    );
  }
}
