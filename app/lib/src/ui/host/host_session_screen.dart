import 'dart:async';

import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/live_host_socket.dart';
import '../../models/live_session.dart';
import '../../models/question_set.dart';
import 'host_report_screen.dart';

/// Host konsolunun canlı ekranı — gözləmə otağı, fərdi templi irəliləmə
/// izləməsi və bitmə vəziyyətinin HAMISINI bir WS bağlantısı üzərində
/// idarə edir (bax dizayn sənədi, Ekran 2-4).
///
/// **Fərdi tempo modeli** (bax `.planning/2026-09-08-masterai-live-session-
/// pacing/`): müəllim sessiyanı başladanda ÜMUMİ bir vaxt büdcəsi təyin
/// edir, hər tələbə öz sürəti ilə öz "Növbəti sual" düyməsi ilə irəliləyir
/// — host artıq paylaşılan bir "cari sual" görmür, yalnız hər kəsin FƏRDİ
/// tərəqqisini (neçə sual bitirib) və ÜMUMİ qalan vaxtı canlı izləyir.
class HostSessionScreen extends StatefulWidget {
  const HostSessionScreen({
    super.key,
    required this.token,
    required this.session,
    required this.questionSet,
  });

  final String token;
  final LiveSessionInfo session;
  final QuestionSetInfo questionSet;

  @override
  State<HostSessionScreen> createState() => _HostSessionScreenState();
}

class _HostSessionScreenState extends State<HostSessionScreen> {
  late final LiveHostSocket _socket;

  String _phase = 'waiting'; // waiting | active | finished
  final Map<int, String> _participantNames = {};
  final Map<int, int> _participantProgress = {};
  int _durationSeconds = 0;
  int _totalQuestions = 0;
  int _remainingSeconds = 0;
  Timer? _tickTimer;
  Map<String, dynamic>? _finished;
  bool _disconnected = false;

  @override
  void initState() {
    super.initState();
    _socket = LiveHostSocket(wsBaseUrl: kWsBaseUrl, pin: widget.session.pin, token: widget.token);
    _socket.events.listen(_handleEvent);
    _socket.errors.listen((msg) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    });
    _socket.onDisconnected.listen((_) {
      if (!mounted) return;
      setState(() => _disconnected = true);
    });
    _socket.connect();
  }

  @override
  void dispose() {
    _tickTimer?.cancel();
    _socket.dispose();
    super.dispose();
  }

  void _handleEvent(Map<String, dynamic> event) {
    switch (event['type']) {
      case 'state':
        final rows = (event['participants'] as List).cast<Map<String, dynamic>>();
        setState(() {
          _participantNames.clear();
          for (final p in rows) {
            _participantNames[p['id'] as int] = p['display_name'] as String;
          }
        });
        break;
      case 'participant_joined':
        setState(() => _participantNames[event['participant_id'] as int] = event['display_name'] as String);
        break;
      case 'started':
        setState(() {
          _phase = 'active';
          _durationSeconds = event['duration_seconds'] as int;
          _totalQuestions = event['total_questions'] as int;
          _remainingSeconds = _durationSeconds;
        });
        _startTicking();
        break;
      case 'participant_progress':
        setState(() {
          _participantProgress[event['participant_id'] as int] = event['answered_count'] as int;
        });
        break;
      case 'finished':
        _tickTimer?.cancel();
        setState(() {
          _phase = 'finished';
          _finished = event;
        });
        break;
    }
  }

  void _startTicking() {
    _tickTimer?.cancel();
    _tickTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_remainingSeconds <= 0) {
        timer.cancel();
        return;
      }
      setState(() => _remainingSeconds -= 1);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.questionSet.title)),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Center(child: _buildBody()),
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_disconnected) {
      return const Text('Bağlantı kəsildi. Səhifəni yeniləyib yenidən cəhd edin.');
    }
    switch (_phase) {
      case 'waiting':
        return _WaitingView(
          pin: widget.session.pin,
          participants: _participantNames.values.toList(),
          onStart: (durationSeconds) => _socket.sendStart(durationSeconds: durationSeconds),
        );
      case 'active':
        return _ActiveView(
          remainingSeconds: _remainingSeconds,
          totalQuestions: _totalQuestions,
          participantNames: _participantNames,
          participantProgress: _participantProgress,
        );
      case 'finished':
        return _FinishedView(
          finished: _finished!,
          onReport: () => Navigator.of(context).pushReplacement(MaterialPageRoute(
            builder: (_) => HostReportScreen(token: widget.token, sessionId: widget.session.id),
          )),
        );
      default:
        return const SizedBox.shrink();
    }
  }
}

class _WaitingView extends StatefulWidget {
  const _WaitingView({required this.pin, required this.participants, required this.onStart});

  final String pin;
  final List<String> participants;
  final ValueChanged<int> onStart;

  @override
  State<_WaitingView> createState() => _WaitingViewState();
}

class _WaitingViewState extends State<_WaitingView> {
  static const _durationOptions = [1, 3, 5, 10];
  int _selectedMinutes = 3;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Sinif bu kodu daxil etsin', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        Text(
          widget.pin,
          style: Theme.of(context).textTheme.displayLarge?.copyWith(
                fontWeight: FontWeight.bold,
                letterSpacing: 8,
              ),
        ),
        const SizedBox(height: 24),
        Text('Qoşulanlar: ${widget.participants.length}', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        SizedBox(
          height: 120,
          child: widget.participants.isEmpty
              ? const Center(child: Text('Hələ heç kim qoşulmayıb…'))
              : ListView(
                  shrinkWrap: true,
                  children: widget.participants.map((name) => Chip(label: Text(name))).toList(),
                ),
        ),
        const SizedBox(height: 24),
        Text('Ümumi vaxt limiti', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: _durationOptions
              .map((minutes) => ChoiceChip(
                    label: Text('$minutes dəqiqə'),
                    selected: _selectedMinutes == minutes,
                    onSelected: (_) => setState(() => _selectedMinutes = minutes),
                  ))
              .toList(),
        ),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: widget.participants.isEmpty ? null : () => widget.onStart(_selectedMinutes * 60),
          child: const Padding(
            padding: EdgeInsets.symmetric(horizontal: 32, vertical: 12),
            child: Text('Başla', style: TextStyle(fontSize: 18)),
          ),
        ),
      ],
    );
  }
}

class _ActiveView extends StatelessWidget {
  const _ActiveView({
    required this.remainingSeconds,
    required this.totalQuestions,
    required this.participantNames,
    required this.participantProgress,
  });

  final int remainingSeconds;
  final int totalQuestions;
  final Map<int, String> participantNames;
  final Map<int, int> participantProgress;

  String _formatTime(int seconds) {
    final m = seconds ~/ 60;
    final s = seconds % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final entries = participantNames.entries.toList()
      ..sort((a, b) => (participantProgress[b.key] ?? 0).compareTo(participantProgress[a.key] ?? 0));
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Qalan vaxt', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(
          _formatTime(remainingSeconds),
          style: Theme.of(context).textTheme.displayMedium?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 24),
        Text('Hər kəs öz sürəti ilə davam edir', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        SizedBox(
          height: 240,
          child: ListView(
            shrinkWrap: true,
            children: entries
                .map((e) => ListTile(
                      title: Text(e.value),
                      trailing: Text('${participantProgress[e.key] ?? 0}/$totalQuestions'),
                    ))
                .toList(),
          ),
        ),
      ],
    );
  }
}

class _FinishedView extends StatelessWidget {
  const _FinishedView({required this.finished, required this.onReport});

  final Map<String, dynamic> finished;
  final VoidCallback onReport;

  @override
  Widget build(BuildContext context) {
    final leaderboard = (finished['leaderboard'] as List).cast<Map<String, dynamic>>();
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Sessiya bitdi!', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        Text('Ümumi sual sayı: ${finished['total_questions']}'),
        const SizedBox(height: 24),
        Text('Yekun sıralama', style: Theme.of(context).textTheme.titleMedium),
        ...leaderboard.asMap().entries.map(
              (e) => Text('${e.key + 1}. ${e.value['display_name']} — ${e.value['score']}'),
            ),
        const SizedBox(height: 24),
        FilledButton(onPressed: onReport, child: const Text('Tam hesabatı gör')),
      ],
    );
  }
}
