import 'package:flutter/material.dart';

import '../../config.dart';
import '../../data/api_exception.dart';
import '../../data/live_client.dart';
import '../../models/live_question.dart';

/// Bir sualın redaktə forması — mətn, 5 variant, düzgün cavab (radio),
/// izah. Bax Sual redaktə/təsdiq ekranı (Faza 5).
class QuestionFormScreen extends StatefulWidget {
  const QuestionFormScreen({super.key, required this.token, required this.question});

  final String token;
  final LiveQuestionInfo question;

  @override
  State<QuestionFormScreen> createState() => _QuestionFormScreenState();
}

class _QuestionFormScreenState extends State<QuestionFormScreen> {
  final _liveClient = LiveClient(baseUrl: kApiBaseUrl);
  late final TextEditingController _questionController;
  late final List<TextEditingController> _optionControllers;
  late final TextEditingController _explanationController;
  late int _correctIndex;

  bool _saving = false;
  String? _error;

  static const _letters = ['A', 'B', 'C', 'D', 'E'];

  @override
  void initState() {
    super.initState();
    _questionController = TextEditingController(text: widget.question.question);
    _optionControllers = widget.question.options.map((o) => TextEditingController(text: o)).toList();
    _explanationController = TextEditingController(text: widget.question.explanation);
    _correctIndex = widget.question.correctIndex;
  }

  @override
  void dispose() {
    _questionController.dispose();
    for (final c in _optionControllers) {
      c.dispose();
    }
    _explanationController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await _liveClient.updateQuestion(
        widget.token,
        widget.question.id,
        question: _questionController.text.trim(),
        options: _optionControllers.map((c) => c.text.trim()).toList(),
        correctIndex: _correctIndex,
        explanation: _explanationController.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sualı redaktə et')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _questionController,
              decoration: const InputDecoration(labelText: 'Sual mətni'),
              maxLines: 3,
              enabled: !_saving,
            ),
            const SizedBox(height: 16),
            Text('Variantlar (düzgün cavabı seçin)', style: Theme.of(context).textTheme.titleSmall),
            RadioGroup<int>(
              groupValue: _correctIndex,
              onChanged: (v) {
                if (_saving) return;
                setState(() => _correctIndex = v ?? _correctIndex);
              },
              child: Column(
                children: [
                  for (var i = 0; i < _optionControllers.length; i++)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Row(
                        children: [
                          Radio<int>(value: i),
                          Expanded(
                            child: TextField(
                              controller: _optionControllers[i],
                              decoration: InputDecoration(labelText: _letters[i]),
                              enabled: !_saving,
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _explanationController,
              decoration: const InputDecoration(labelText: 'İzah'),
              maxLines: 3,
              enabled: !_saving,
            ),
            if (_error != null) ...[
              const SizedBox(height: 16),
              Text(_error!, style: const TextStyle(color: Colors.red)),
            ],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Yadda saxla'),
            ),
          ],
        ),
      ),
    );
  }
}
