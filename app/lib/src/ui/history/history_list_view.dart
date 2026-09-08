import 'package:flutter/material.dart';

import '../../models/history.dart';
import '../../theme/app_subject_colors.dart';

/// Canlı sessiya + ev tapşırığı nəticələrinin birləşdirilmiş siyahısı —
/// `MyHistoryScreen` VƏ `StudentHistoryScreen` bunu paylaşır (yalnız
/// data mənbəyi fərqlidir, bax həmin ekranlar).
class HistoryListView extends StatelessWidget {
  const HistoryListView({super.key, required this.entries});

  final List<HistoryEntry> entries;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Hələ heç bir nəticə yoxdur.', textAlign: TextAlign.center),
        ),
      );
    }
    return ListView.separated(
      itemCount: entries.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final e = entries[index];
        return ListTile(
          leading: CircleAvatar(
            backgroundColor: subjectColor(context, e.subject),
            foregroundColor: subjectColorForeground(context),
            child: Icon(e.kind == 'live' ? Icons.groups : Icons.assignment),
          ),
          title: Text('${e.subjectLabel} — ${e.title}'),
          subtitle: Text(
            '${e.kind == 'live' ? 'Canlı sessiya' : 'Ev tapşırığı'} · '
            '${e.score}/${e.totalQuestions} xal · ${e.date}',
          ),
        );
      },
    );
  }
}
