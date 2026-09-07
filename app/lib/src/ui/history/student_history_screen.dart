import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/history_client.dart';
import '../../models/history.dart';
import 'history_list_view.dart';

/// Müəllimin bir tələbənin tarixçəsinə baxması (`GET
/// /history/student/{id}`, yalnız ortaq çatı olan tələbələr üçün icazə
/// verilir — bax `server/app.py`, `get_student_history`).
class StudentHistoryScreen extends StatefulWidget {
  const StudentHistoryScreen({super.key, required this.token, required this.studentId, required this.displayName});

  final String token;
  final int studentId;
  final String displayName;

  @override
  State<StudentHistoryScreen> createState() => _StudentHistoryScreenState();
}

class _StudentHistoryScreenState extends State<StudentHistoryScreen> {
  final _client = HistoryClient(baseUrl: kApiBaseUrl);
  late Future<List<HistoryEntry>> _future;

  @override
  void initState() {
    super.initState();
    _future = _client.getStudentHistory(widget.token, widget.studentId);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('${widget.displayName} — tarixçə')),
      body: FutureBuilder<List<HistoryEntry>>(
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
          return HistoryListView(entries: snapshot.data!);
        },
      ),
    );
  }
}
