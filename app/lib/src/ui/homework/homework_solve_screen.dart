import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/homework_client.dart';
import '../../models/homework.dart';

/// Ev tapşırığının həll ekranı — `POST .../start` ilə açılır (fasilə
/// verilmişdirsə HARADA QALDIĞINDAN davam edir), hər cavabdan sonra
/// DƏRHAL nəticə göstərir, qısa gecikmədən sonra avtomatik növbəti
/// suala keçir (bax dizayn sənədi — vaxt sayğacı YOXDUR, asinxron
/// rejimdir).
class HomeworkSolveScreen extends StatefulWidget {
  const HomeworkSolveScreen({super.key, required this.token, required this.assignment});

  final String token;
  final MyAssignmentInfo assignment;

  @override
  State<HomeworkSolveScreen> createState() => _HomeworkSolveScreenState();
}

class _HomeworkSolveScreenState extends State<HomeworkSolveScreen> {
  final _client = HomeworkClient(baseUrl: kApiBaseUrl);

  bool _loading = true;
  String? _error;
  int? _attemptId;
  int _score = 0;
  HomeworkQuestionPayload? _question;
  HomeworkAnswerResult? _lastResult;
  int? _selectedIndex;
  bool _finished = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    try {
      final state = await _client.startAttempt(widget.token, widget.assignment.assignmentId);
      if (!mounted) return;
      setState(() {
        _attemptId = state.attemptId;
        _score = state.score;
        _question = state.question;
        _finished = state.question == null;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _selectAnswer(int index) async {
    if (_selectedIndex != null || _question == null) return;
    setState(() => _selectedIndex = index);
    try {
      final result = await _client.answer(
        widget.token,
        attemptId: _attemptId!,
        questionIndex: _question!.index,
        chosenIndex: index,
      );
      if (!mounted) return;
      setState(() {
        _lastResult = result;
        if (result.isCorrect) _score += 1;
      });
      await Future.delayed(const Duration(seconds: 2));
      if (!mounted) return;
      setState(() {
        _question = result.nextQuestion;
        _lastResult = null;
        _selectedIndex = null;
        _finished = result.nextQuestion == null;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      setState(() => _selectedIndex = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('${widget.assignment.subject} — ${widget.assignment.title}')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Center(child: _buildBody()),
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) return const CircularProgressIndicator();
    if (_error != null) return Text(_error!, style: const TextStyle(color: Colors.red));
    if (_finished) return _FinishedView(score: _score);
    return _QuestionView(
      question: _question!,
      score: _score,
      selectedIndex: _selectedIndex,
      result: _lastResult,
      onSelect: _selectAnswer,
    );
  }
}

class _QuestionView extends StatelessWidget {
  const _QuestionView({
    required this.question,
    required this.score,
    required this.selectedIndex,
    required this.result,
    required this.onSelect,
  });

  final HomeworkQuestionPayload question;
  final int score;
  final int? selectedIndex;
  final HomeworkAnswerResult? result;
  final void Function(int index) onSelect;

  static const _letters = ['A', 'B', 'C', 'D', 'E'];

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Sual ${question.index + 1}/${question.total} · Xal: $score',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 16),
        Text(
          question.question,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 24),
        for (var i = 0; i < question.options.length; i++) ...[
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: result != null && i == result!.correctIndex
                  ? Colors.green
                  : (selectedIndex == i ? Colors.red : null),
              padding: const EdgeInsets.symmetric(vertical: 16),
            ),
            onPressed: selectedIndex == null ? () => onSelect(i) : null,
            child: Text('${_letters[i]}) ${question.options[i]}'),
          ),
          const SizedBox(height: 8),
        ],
        if (result != null) ...[
          const SizedBox(height: 8),
          Text(
            result!.isCorrect ? 'Düzgün! 🎉' : 'Səhv',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              color: result!.isCorrect ? Colors.green : Colors.red,
            ),
          ),
          const SizedBox(height: 4),
          Text(result!.explanation, textAlign: TextAlign.center),
        ],
      ],
    );
  }
}

class _FinishedView extends StatelessWidget {
  const _FinishedView({required this.score});

  final int score;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.celebration, size: 64, color: Colors.amber),
        const SizedBox(height: 16),
        Text('Tapşırıq tamamlandı!', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        Text('Xalınız: $score', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Geri qayıt'),
        ),
      ],
    );
  }
}
