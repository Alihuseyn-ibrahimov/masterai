import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/badge_client.dart';
import '../../models/badge.dart';

/// Tələbənin öz nailiyyət nişanları (Faza 6) — qazanılan (rəngli) /
/// qazanılmayan (boz, kölgəli) kartlar grid-i.
class MyBadgesScreen extends StatefulWidget {
  const MyBadgesScreen({super.key, required this.token});

  final String token;

  @override
  State<MyBadgesScreen> createState() => _MyBadgesScreenState();
}

class _MyBadgesScreenState extends State<MyBadgesScreen> {
  final _client = BadgeClient(baseUrl: kApiBaseUrl);
  late Future<List<BadgeInfo>> _future;

  @override
  void initState() {
    super.initState();
    _future = _client.getMyBadges(widget.token);
  }

  void _refresh() => setState(() => _future = _client.getMyBadges(widget.token));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Nailiyyətlərim'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh, tooltip: 'Yenilə')],
      ),
      body: FutureBuilder<List<BadgeInfo>>(
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
          final badges = snapshot.data!;
          return GridView.builder(
            padding: const EdgeInsets.all(16),
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              mainAxisSpacing: 12,
              crossAxisSpacing: 12,
              childAspectRatio: 0.95,
            ),
            itemCount: badges.length,
            itemBuilder: (context, index) => _BadgeCard(badge: badges[index]),
          );
        },
      ),
    );
  }
}

class _BadgeCard extends StatelessWidget {
  const _BadgeCard({required this.badge});

  final BadgeInfo badge;

  @override
  Widget build(BuildContext context) {
    final meta = badge.meta;
    final colorScheme = Theme.of(context).colorScheme;
    return Opacity(
      opacity: badge.earned ? 1 : 0.45,
      child: Card(
        color: badge.earned ? colorScheme.primaryContainer : null,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(meta.emoji, style: const TextStyle(fontSize: 40)),
              const SizedBox(height: 8),
              Text(
                meta.title,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 4),
              Text(
                meta.description,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
