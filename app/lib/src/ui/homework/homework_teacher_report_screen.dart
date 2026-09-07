import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/homework_client.dart';
import '../../models/homework.dart';

/// Müəllimin bir tapşırığa baxdığı hesabat — hər çat üzvünün statusu
/// (gözləyir/davam edir/tamamlanıb) və xalı (bax Ev Təkrarı Rejimi
/// dizayn sənədi, "Tapşırıq hesabatı").
class HomeworkTeacherReportScreen extends StatefulWidget {
  const HomeworkTeacherReportScreen({super.key, required this.token, required this.assignmentId});

  final String token;
  final int assignmentId;

  @override
  State<HomeworkTeacherReportScreen> createState() => _HomeworkTeacherReportScreenState();
}

class _HomeworkTeacherReportScreenState extends State<HomeworkTeacherReportScreen> {
  final _client = HomeworkClient(baseUrl: kApiBaseUrl);
  late Future<List<HomeworkReportRow>> _future;

  @override
  void initState() {
    super.initState();
    _future = _client.getReport(widget.token, widget.assignmentId);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Tapşırıq hesabatı')),
      body: FutureBuilder<List<HomeworkReportRow>>(
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
          final rows = snapshot.data!;
          if (rows.isEmpty) {
            return const Center(child: Text('Bu çatda üzv yoxdur.'));
          }
          return ListView.separated(
            itemCount: rows.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (context, index) {
              final row = rows[index];
              return ListTile(
                leading: CircleAvatar(
                  backgroundColor: row.status == 'tamamlanıb' ? Colors.green : null,
                  child: Icon(row.status == 'tamamlanıb' ? Icons.check : Icons.hourglass_empty),
                ),
                title: Text(row.displayName),
                subtitle: Text(row.status),
                trailing: row.score != null ? Text('${row.score} xal') : null,
              );
            },
          );
        },
      ),
    );
  }
}
