import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/live_client.dart';
import '../../models/live_session.dart';

/// Sessiya sonu tam hesabatı — yekun sıralama + sual-sual təhlil (ən çox
/// seçilən səhv variant daxil). Bax dizayn sənədi, "Sessiya sonu
/// hesabatı" bölməsi.
class HostReportScreen extends StatefulWidget {
  const HostReportScreen({super.key, required this.token, required this.sessionId});

  final String token;
  final int sessionId;

  @override
  State<HostReportScreen> createState() => _HostReportScreenState();
}

class _HostReportScreenState extends State<HostReportScreen> {
  final _liveClient = LiveClient(baseUrl: kApiBaseUrl);
  late Future<LiveSessionReport> _reportFuture;

  static const _letters = ['A', 'B', 'C', 'D', 'E'];

  @override
  void initState() {
    super.initState();
    _reportFuture = _liveClient.getReport(widget.token, widget.sessionId);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sessiya hesabatı')),
      body: FutureBuilder<LiveSessionReport>(
        future: _reportFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            final message =
                snapshot.error is ApiException ? (snapshot.error as ApiException).message : 'Xəta baş verdi';
            return Center(child: Text(message));
          }
          final report = snapshot.data!;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text('Yekun sıralama', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              ...report.rankings.map(
                (row) => ListTile(
                  leading: CircleAvatar(child: Text(row.rank.toString())),
                  title: Text(row.displayName),
                  trailing: Text('${row.score}/${report.totalQuestions}'),
                ),
              ),
              const Divider(height: 32),
              Text('Sual-sual təhlil', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              ...report.perQuestion.map(_buildQuestionCard),
            ],
          );
        },
      ),
    );
  }

  Widget _buildQuestionCard(LiveQuestionReport q) {
    final wrongLabel =
        q.mostCommonWrongIndex != null ? _letters[q.mostCommonWrongIndex!] : null;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${q.index + 1}. ${q.question}', style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text('Düzgün cavab: ${_letters[q.correctIndex]}'),
            Text('${q.correctCount}/${q.totalAnswers} düzgün cavabladı'),
            if (wrongLabel != null) Text('Ən çox seçilən səhv variant: $wrongLabel'),
          ],
        ),
      ),
    );
  }
}
