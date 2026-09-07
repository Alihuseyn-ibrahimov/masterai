import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/live_host_socket.dart';
import '../../models/live_session.dart';
import '../../models/question_set.dart';
import 'host_report_screen.dart';

/// Host konsolunun canlı ekranı — gözləmə otağı, sual göstərimi, nəticə
/// və bitmə vəziyyətlərinin HAMISINI bir WS bağlantısı üzərində idarə
/// edir (bax dizayn sənədi, Ekran 2-4).
///
/// **Bilinən Faza-1 sadələşdirməsi:** `result` hadisəsi (düzgün cavab
/// açıqlanması) və növbəti sualın broadcast-ı backend-də EYNİ
/// `advance_question` çağırışında ardıcıl baş verir (bax
/// `server/live_session_runner.py`, mövcud `quiz_runner.py` naxışının
/// təkrarı) — müəllim nəticə ekranında "dayanıb müzakirə etmək" üçün
/// ayrıca vaxt qazana bilmir, `result` demək olar ki dərhal növbəti
/// `question`/`finished` ilə əvəzlənir. Bu, Faza-2+ üçün mümkün
/// təkmilləşdirmədir (ayrıca "aç"/"davam et" addımları), hazırkı MVP-nin
/// əhatəsində deyil.
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

  String _phase = 'waiting'; // waiting | question | result | finished
  final List<String> _participants = [];
  Map<String, dynamic>? _question;
  int _answeredCount = 0;
  int _totalParticipants = 0;
  Map<String, dynamic>? _result;
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
    _socket.dispose();
    super.dispose();
  }

  void _handleEvent(Map<String, dynamic> event) {
    switch (event['type']) {
      case 'state':
        final rows = (event['participants'] as List).cast<Map<String, dynamic>>();
        setState(() => _participants
          ..clear()
          ..addAll(rows.map((p) => p['display_name'] as String)));
        break;
      case 'participant_joined':
        setState(() => _participants.add(event['display_name'] as String));
        break;
      case 'question':
        setState(() {
          _phase = 'question';
          _question = event;
          _answeredCount = 0;
          _totalParticipants = _participants.length;
        });
        break;
      case 'answer_progress':
        setState(() {
          _answeredCount = event['answered_count'] as int;
          _totalParticipants = event['total_participants'] as int;
        });
        break;
      case 'result':
        setState(() {
          _phase = 'result';
          _result = event;
        });
        break;
      case 'finished':
        setState(() {
          _phase = 'finished';
          _finished = event;
        });
        break;
    }
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
          participants: _participants,
          onStart: _socket.sendStart,
        );
      case 'question':
        return _QuestionView(
          question: _question!,
          answeredCount: _answeredCount,
          totalParticipants: _totalParticipants,
          onNext: _socket.sendNext,
        );
      case 'result':
        return _ResultView(result: _result!);
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

class _WaitingView extends StatelessWidget {
  const _WaitingView({required this.pin, required this.participants, required this.onStart});

  final String pin;
  final List<String> participants;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Sinif bu kodu daxil etsin', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        Text(
          pin,
          style: Theme.of(context).textTheme.displayLarge?.copyWith(
                fontWeight: FontWeight.bold,
                letterSpacing: 8,
              ),
        ),
        const SizedBox(height: 24),
        Text('Qoşulanlar: ${participants.length}', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        SizedBox(
          height: 160,
          child: participants.isEmpty
              ? const Center(child: Text('Hələ heç kim qoşulmayıb…'))
              : ListView(
                  shrinkWrap: true,
                  children: participants.map((name) => Chip(label: Text(name))).toList(),
                ),
        ),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: participants.isEmpty ? null : onStart,
          child: const Padding(
            padding: EdgeInsets.symmetric(horizontal: 32, vertical: 12),
            child: Text('Başla', style: TextStyle(fontSize: 18)),
          ),
        ),
      ],
    );
  }
}

class _QuestionView extends StatelessWidget {
  const _QuestionView({
    required this.question,
    required this.answeredCount,
    required this.totalParticipants,
    required this.onNext,
  });

  final Map<String, dynamic> question;
  final int answeredCount;
  final int totalParticipants;
  final VoidCallback onNext;

  static const _letters = ['A', 'B', 'C', 'D', 'E'];

  @override
  Widget build(BuildContext context) {
    final options = (question['options'] as List).cast<String>();
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          'Sual ${(question['index'] as int) + 1}/${question['total']}',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),
        Text(
          question['question'] as String,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 24),
        ...List.generate(
          options.length,
          (i) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Text('${_letters[i]}) ${options[i]}', style: Theme.of(context).textTheme.bodyLarge),
          ),
        ),
        const SizedBox(height: 24),
        Text('Cavab verənlər: $answeredCount/$totalParticipants'),
        const SizedBox(height: 16),
        FilledButton(onPressed: onNext, child: const Text('Növbəti sual')),
      ],
    );
  }
}

class _ResultView extends StatelessWidget {
  const _ResultView({required this.result});

  final Map<String, dynamic> result;

  static const _letters = ['A', 'B', 'C', 'D', 'E'];

  @override
  Widget build(BuildContext context) {
    final correctIndex = result['correct_index'] as int;
    final leaderboard = (result['leaderboard'] as List).cast<Map<String, dynamic>>();
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Düzgün cavab: ${_letters[correctIndex]}', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 8),
        Text(result['explanation'] as String, textAlign: TextAlign.center),
        const SizedBox(height: 24),
        Text('Liderlik lövhəsi', style: Theme.of(context).textTheme.titleMedium),
        ...leaderboard.map(
          (row) => Text('${row['display_name']} — ${row['score']}'),
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
