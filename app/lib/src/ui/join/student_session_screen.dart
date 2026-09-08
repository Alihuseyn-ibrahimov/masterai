import 'dart:async';

import 'package:flutter/material.dart';

import '../../data/live_play_socket.dart';

/// Tələbənin canlı sessiya ekranı — gözləmə/sual/nəticə/fərdi-bitmə/bitmə
/// vəziyyətlərinin HAMISINI `JoinPinScreen`-də artıq qoşulmuş TƏK WS
/// bağlantısı üzərində idarə edir (bax `HostSessionScreen`-in eyni
/// naxışı).
///
/// **Fərdi tempo modeli** (bax `.planning/2026-09-08-masterai-live-session-
/// pacing/`): sual-üzrə vaxt sayğacı VƏ cavabdan sonrakı avtomatik keçid
/// TAM LƏĞV OLUNUB — tələbə nəticəni gördükdən sonra öz sürəti ilə
/// "Növbəti sual" düyməsinə basaraq irəliləyir. Yalnız BİR ÜMUMİ
/// (sessiya-səviyyəli) qalan vaxt göstərilir, server hər sual göndərəndə
/// bunu təzələyir (`remaining_seconds`).
class StudentSessionScreen extends StatefulWidget {
  const StudentSessionScreen({
    super.key,
    required this.socket,
    required this.participantId,
    required this.displayName,
  });

  final LivePlaySocket socket;
  final int participantId;
  final String displayName;

  @override
  State<StudentSessionScreen> createState() => _StudentSessionScreenState();
}

class _StudentSessionScreenState extends State<StudentSessionScreen> {
  String _phase = 'waiting'; // waiting | question | result | personal_finished | finished
  Map<String, dynamic>? _question;
  int? _selectedIndex;
  bool _answered = false;
  Timer? _countdownTimer;
  int _remainingSeconds = 0;
  Map<String, dynamic>? _result;
  Map<String, dynamic>? _personalFinished;
  Map<String, dynamic>? _finished;
  bool _disconnected = false;
  String? _liveError;

  @override
  void initState() {
    super.initState();
    widget.socket.events.listen(_handleEvent);
    widget.socket.errors.listen((msg) {
      if (!mounted) return;
      setState(() => _liveError = msg);
    });
    widget.socket.onDisconnected.listen((_) {
      if (!mounted) return;
      setState(() => _disconnected = true);
    });
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    widget.socket.dispose();
    super.dispose();
  }

  void _startCountdown(int remainingSeconds) {
    _countdownTimer?.cancel();
    setState(() => _remainingSeconds = remainingSeconds);
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_remainingSeconds <= 0) {
        timer.cancel();
        return;
      }
      setState(() => _remainingSeconds -= 1);
    });
  }

  void _handleEvent(Map<String, dynamic> event) {
    switch (event['type']) {
      case 'question':
        _countdownTimer?.cancel();
        setState(() {
          _phase = 'question';
          _question = event;
          _selectedIndex = null;
          _answered = false;
          _liveError = null;
        });
        _startCountdown((event['remaining_seconds'] as num).round());
        break;
      case 'result':
        _countdownTimer?.cancel();
        setState(() {
          _phase = 'result';
          _result = event;
        });
        break;
      case 'personal_finished':
        _countdownTimer?.cancel();
        setState(() {
          _phase = 'personal_finished';
          _personalFinished = event;
        });
        break;
      case 'finished':
        _countdownTimer?.cancel();
        setState(() {
          _phase = 'finished';
          _finished = event;
        });
        break;
    }
  }

  void _selectAnswer(int index) {
    if (_answered) return;
    setState(() {
      _selectedIndex = index;
      _answered = true;
    });
    widget.socket.sendAnswer(questionIndex: _question!['index'] as int, chosenIndex: index);
  }

  void _requestNext() {
    widget.socket.sendNext();
  }

  /// Naviqasiya yığınının İLK ekranına qayıdır — bu, giriş ekranından
  /// ƏVVƏL qoşulanda `LoginScreen`, daxil olmuş istifadəçi üçün isə
  /// `ChatListScreen`-dir (bax `chat_list_screen.dart`-dakı "Sinif
  /// sessiyasına qoşul" giriş nöqtəsi) — sabit `LoginScreen`-ə
  /// yönləndirmə artıq daxil olmuş istifadəçini səhvən çıxış etdirirdi.
  void _leave() {
    Navigator.of(context).popUntil((route) => route.isFirst);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.displayName)),
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
      return const Text('Bağlantı kəsildi. Yenidən qoşulmaq üçün geri qayıdın.');
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_liveError != null) ...[
          Text(_liveError!, style: const TextStyle(color: Colors.red)),
          const SizedBox(height: 12),
        ],
        switch (_phase) {
          'waiting' => const _WaitingView(),
          'question' => _QuestionView(
              question: _question!,
              remainingSeconds: _remainingSeconds,
              selectedIndex: _selectedIndex,
              answered: _answered,
              onSelect: _selectAnswer,
            ),
          'result' => _ResultView(result: _result!, onNext: _requestNext),
          'personal_finished' => _PersonalFinishedView(personalFinished: _personalFinished!),
          'finished' => _FinishedView(finished: _finished!, participantId: widget.participantId, onLeave: _leave),
          _ => const SizedBox.shrink(),
        },
      ],
    );
  }
}

String _formatTime(int seconds) {
  final safeSeconds = seconds < 0 ? 0 : seconds;
  final m = safeSeconds ~/ 60;
  final s = safeSeconds % 60;
  return '$m:${s.toString().padLeft(2, '0')}';
}

class _WaitingView extends StatelessWidget {
  const _WaitingView();

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const CircularProgressIndicator(),
        const SizedBox(height: 16),
        Text('Qoşuldunuz! Müəllimin başlatmasını gözləyin…', style: Theme.of(context).textTheme.titleMedium),
      ],
    );
  }
}

class _QuestionView extends StatelessWidget {
  const _QuestionView({
    required this.question,
    required this.remainingSeconds,
    required this.selectedIndex,
    required this.answered,
    required this.onSelect,
  });

  final Map<String, dynamic> question;
  final int remainingSeconds;
  final int? selectedIndex;
  final bool answered;
  final void Function(int index) onSelect;

  static const _letters = ['A', 'B', 'C', 'D', 'E'];
  static const _colors = [Colors.red, Colors.blue, Colors.orange, Colors.green, Colors.purple];

  @override
  Widget build(BuildContext context) {
    final options = (question['options'] as List).cast<String>();
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              'Sual ${(question['index'] as int) + 1}/${question['total']}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text('⏱ ${_formatTime(remainingSeconds)}', style: Theme.of(context).textTheme.titleMedium),
          ],
        ),
        const SizedBox(height: 16),
        Text(
          question['question'] as String,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 24),
        for (var i = 0; i < options.length; i++) ...[
          AnimatedScale(
            scale: selectedIndex == i ? 1.04 : 1,
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOutBack,
            child: FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: selectedIndex == i ? _colors[i % _colors.length] : null,
                padding: const EdgeInsets.symmetric(vertical: 20),
                textStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
              ),
              onPressed: answered ? null : () => onSelect(i),
              child: Text('${_letters[i]}) ${options[i]}'),
            ),
          ),
          const SizedBox(height: 8),
        ],
        if (answered) ...[
          const SizedBox(height: 8),
          const Text('Cavabınız göndərildi, nəticə gözlənilir…'),
        ],
      ],
    );
  }
}

class _ResultView extends StatelessWidget {
  const _ResultView({required this.result, required this.onNext});

  final Map<String, dynamic> result;
  final VoidCallback onNext;

  static const _letters = ['A', 'B', 'C', 'D', 'E'];

  @override
  Widget build(BuildContext context) {
    final correctIndex = result['correct_index'] as int;
    final isCorrect = result['is_correct'] as bool;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        TweenAnimationBuilder<double>(
          tween: Tween(begin: 0.5, end: 1),
          duration: const Duration(milliseconds: 350),
          curve: Curves.elasticOut,
          builder: (context, scale, child) => Transform.scale(scale: scale, child: child),
          child: Text(
            isCorrect ? 'Düzgün! 🎉' : 'Səhv',
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  color: isCorrect ? Colors.green : Colors.red,
                ),
          ),
        ),
        const SizedBox(height: 8),
        Text('Düzgün cavab: ${_letters[correctIndex]}'),
        const SizedBox(height: 8),
        Text(result['explanation'] as String, textAlign: TextAlign.center),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: onNext,
          child: const Padding(
            padding: EdgeInsets.symmetric(horizontal: 32, vertical: 12),
            child: Text('Növbəti sual', style: TextStyle(fontSize: 16)),
          ),
        ),
      ],
    );
  }
}

class _PersonalFinishedView extends StatelessWidget {
  const _PersonalFinishedView({required this.personalFinished});

  final Map<String, dynamic> personalFinished;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          'Bitirdiniz! ${personalFinished['correct_count']}/${personalFinished['total_questions']} düzgün',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 24),
        const CircularProgressIndicator(),
        const SizedBox(height: 16),
        Text(
          'Digər iştirakçılar hələ davam edir, gözləyin…',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleMedium,
        ),
      ],
    );
  }
}

class _FinishedView extends StatelessWidget {
  const _FinishedView({required this.finished, required this.participantId, required this.onLeave});

  final Map<String, dynamic> finished;
  final int participantId;
  final VoidCallback onLeave;

  @override
  Widget build(BuildContext context) {
    final leaderboard = (finished['leaderboard'] as List).cast<Map<String, dynamic>>();
    final ownIndex = leaderboard.indexWhere((row) => row['participant_id'] == participantId);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Sessiya bitdi!', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        Text('Ümumi sual sayı: ${finished['total_questions']}'),
        const SizedBox(height: 16),
        if (ownIndex != -1)
          Text(
            'Sizin yekun sıranız: ${ownIndex + 1}/${leaderboard.length} — ${leaderboard[ownIndex]['score']} xal',
            style: Theme.of(context).textTheme.titleLarge,
          ),
        const SizedBox(height: 24),
        Text('Tam sıralama', style: Theme.of(context).textTheme.titleMedium),
        ...leaderboard.asMap().entries.map(
              (e) => Text('${e.key + 1}. ${e.value['display_name']} — ${e.value['score']}'),
            ),
        const SizedBox(height: 24),
        FilledButton(onPressed: onLeave, child: const Text('Çıx')),
      ],
    );
  }
}
