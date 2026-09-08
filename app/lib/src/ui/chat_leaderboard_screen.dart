import 'package:flutter/material.dart';

import '../config.dart';
import '../data/api_exception.dart';
import '../data/chat_client.dart';
import '../models/chat.dart';
import '../models/leaderboard.dart';

/// Bir çatın liderlik lövhəsi — yalnız ev tapşırığı xalları (bax Faza 6
/// dizayn sənədi, "canlı sessiyalar çata bağlı deyil"). Bütün çat
/// üzvləri üçün açıqdır (yalnız müəllim deyil).
class ChatLeaderboardScreen extends StatefulWidget {
  const ChatLeaderboardScreen({super.key, required this.token, required this.chat});

  final String token;
  final ChatInfo chat;

  @override
  State<ChatLeaderboardScreen> createState() => _ChatLeaderboardScreenState();
}

class _ChatLeaderboardScreenState extends State<ChatLeaderboardScreen> {
  final _chatClient = ChatClient(baseUrl: kApiBaseUrl);
  late Future<List<LeaderboardRow>> _future;

  @override
  void initState() {
    super.initState();
    _future = _chatClient.getLeaderboard(widget.token, widget.chat.id);
  }

  void _refresh() => setState(() => _future = _chatClient.getLeaderboard(widget.token, widget.chat.id));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.chat.name ?? 'Çat'} — Liderlik lövhəsi'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh, tooltip: 'Yenilə')],
      ),
      body: FutureBuilder<List<LeaderboardRow>>(
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
                leading: CircleAvatar(child: Text('${row.rank}')),
                title: Text(row.rank == 1 ? '👑 ${row.displayName}' : row.displayName),
                trailing: Text('${row.totalScore} xal', style: Theme.of(context).textTheme.titleMedium),
              );
            },
          );
        },
      ),
    );
  }
}
