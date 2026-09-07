import 'dart:async';

import 'package:flutter/material.dart';

import '../../data/live_play_socket.dart';

/// Server-tərəfli timeout-un (bax `server/live_session_runner.py`,
/// `DEFAULT_QUESTION_TIMEOUT_SECONDS`) YALNIZ vizual təxmini əksidir —
/// geri sayım zolağı sırf UI bəzəyidir, real vaxt aşımını SERVER
/// idarə edir (bu ekran heç nə "gec" göndərmir, sadəcə düymələri
/// bağlayır).
const _kQuestionTimeoutSeconds = 20;

/// Tələbənin canlı sessiya ekranı — gözləmə/sual/nəticə/bitmə
/// vəziyyətlərinin HAMISINI `JoinPinScreen`-də artıq qoşulmuş TƏK WS
/// bağlantısı üzərində idarə edir (bax `HostSessionScreen`-in eyni
/// naxışı).
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
  String _phase = 'waiting'; // waiting | question | result | finished
  Map<String, dynamic>? _question;
  int? _selectedIndex;
  bool _answered = false;
  Timer? _countdownTimer;
  int _remainingSeconds = _kQuestionTimeoutSeconds;
  Map<String, dynamic>? _result;
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

  void _startCountdown() {
    _countdownTimer?.cancel();
    setState(() => _remainingSeconds = _kQuestionTimeoutSeconds);
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
        setState(() {
          _phase = 'question';
          _question = event;
          _selectedIndex = null;
          _answered = false;
          _liveError = null;
        });
        _startCountdown();
        break;
      case 'result':
        _countdownTimer?.cancel();
        setState(() {
          _phase = 'result';
          _result = event;
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
          'result' => _ResultView(result: _result!, selectedIndex: _selectedIndex, participantId: widget.participantId),
          'finished' => _FinishedView(finished: _finished!, participantId: widget.participantId, onLeave: _leave),
          _ => const SizedBox.shrink(),
        },
      ],
    );
  }
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
        Text(
          'Sual ${(question['index'] as int) + 1}/${question['total']}',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(value: remainingSeconds / _kQuestionTimeoutSeconds),
        const SizedBox(height: 16),
        Text(
          question['question'] as String,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 24),
        for (var i = 0; i < options.length; i++) ...[
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: selectedIndex == i ? _colors[i % _colors.length] : null,
              padding: const EdgeInsets.symmetric(vertical: 16),
            ),
            onPressed: answered ? null : () => onSelect(i),
            child: Text('${_letters[i]}) ${options[i]}'),
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
  const _ResultView({required this.result, required this.selectedIndex, required this.participantId});

  final Map<String, dynamic> result;
  final int? selectedIndex;
  final int participantId;

  static const _letters = ['A', 'B', 'C', 'D', 'E'];

  @override
  Widget build(BuildContext context) {
    final correctIndex = result['correct_index'] as int;
    final wasCorrect = selectedIndex == correctIndex;
    final leaderboard = (result['leaderboard'] as List).cast<Map<String, dynamic>>();
    final ownRow = leaderboard.cast<Map<String, dynamic>?>().firstWhere(
          (row) => row!['participant_id'] == participantId,
          orElse: () => null,
        );
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          selectedIndex == null ? 'Cavab vermədiniz' : (wasCorrect ? 'Düzgün! 🎉' : 'Səhv'),
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                color: selectedIndex == null ? null : (wasCorrect ? Colors.green : Colors.red),
              ),
        ),
        const SizedBox(height: 8),
        Text('Düzgün cavab: ${_letters[correctIndex]}'),
        const SizedBox(height: 8),
        Text(result['explanation'] as String, textAlign: TextAlign.center),
        const SizedBox(height: 24),
        if (ownRow != null)
          Text('Sizin sıranız: ${leaderboard.indexOf(ownRow) + 1} — ${ownRow['score']} xal')
        else
          const Text('Cavabınız qeydə alındı (liderlik lövhəsinin ilk 5-i arasında deyilsiniz).'),
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
