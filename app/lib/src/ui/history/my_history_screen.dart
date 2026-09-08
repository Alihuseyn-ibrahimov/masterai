import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/history_client.dart';
import '../../models/history.dart';
import '../badges/my_badges_screen.dart';
import 'history_list_view.dart';

/// Tələbənin öz keçmiş nəticələri (canlı sessiya + ev tapşırığı) —
/// bax Fərdi tələbə tarixçəsi.
class MyHistoryScreen extends StatefulWidget {
  const MyHistoryScreen({super.key, required this.token});

  final String token;

  @override
  State<MyHistoryScreen> createState() => _MyHistoryScreenState();
}

class _MyHistoryScreenState extends State<MyHistoryScreen> {
  final _client = HistoryClient(baseUrl: kApiBaseUrl);
  late Future<List<HistoryEntry>> _future;

  @override
  void initState() {
    super.initState();
    _future = _client.getMyHistory(widget.token);
  }

  void _refresh() => setState(() => _future = _client.getMyHistory(widget.token));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mənim tarixçəm'),
        actions: [
          IconButton(
            icon: const Icon(Icons.emoji_events),
            tooltip: 'Nailiyyətlərim',
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => MyBadgesScreen(token: widget.token),
            )),
          ),
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh, tooltip: 'Yenilə'),
        ],
      ),
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
