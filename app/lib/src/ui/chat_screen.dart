import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../config.dart';
import '../data/api_exception.dart';
import '../data/chat_socket.dart';
import '../data/material_client.dart';
import '../data/quiz_client.dart';
import '../models/chat.dart';
import '../models/chat_item.dart';
import '../models/material.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, required this.chat, required this.token, required this.userId});

  final ChatInfo chat;
  final String token;
  final int userId;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  late final ChatSocket _socket;
  final _materialClient = MaterialClient(baseUrl: kApiBaseUrl);
  final _quizClient = QuizClient(baseUrl: kApiBaseUrl);
  final _textController = TextEditingController();
  final _scrollController = ScrollController();

  StreamSubscription<ChatItem>? _itemsSub;
  StreamSubscription<String>? _errorsSub;
  StreamSubscription<void>? _disconnectSub;

  final List<ChatItem> _items = [];
  final Set<int> _answeredQuestionIds = {};
  bool _connected = true;

  @override
  void initState() {
    super.initState();
    _socket = ChatSocket(wsBaseUrl: kWsBaseUrl, chatId: widget.chat.id, token: widget.token);
    _itemsSub = _socket.items.listen(_onItem);
    _errorsSub = _socket.errors.listen(_onSocketError);
    _disconnectSub = _socket.onDisconnected.listen((_) {
      if (mounted) setState(() => _connected = false);
    });
    _socket.connect();
  }

  @override
  void dispose() {
    _itemsSub?.cancel();
    _errorsSub?.cancel();
    _disconnectSub?.cancel();
    _socket.dispose();
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onItem(ChatItem item) {
    if (!mounted) return;
    setState(() => _items.add(item));
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
  }

  void _onSocketError(String detail) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(detail)));
  }

  void _scrollToBottom() {
    if (!_scrollController.hasClients) return;
    _scrollController.animateTo(
      _scrollController.position.maxScrollExtent,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
    );
  }

  void _sendText() {
    final text = _textController.text.trim();
    if (text.isEmpty) return;
    _socket.sendText(text);
    _textController.clear();
  }

  void _answerQuestion(int questionId, int chosenIndex) {
    if (_answeredQuestionIds.contains(questionId)) return;
    setState(() => _answeredQuestionIds.add(questionId));
    _socket.sendAnswer(questionId: questionId, chosenIndex: chosenIndex);
  }

  Future<void> _openMaterialsSheet() async {
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => _MaterialsSheet(
        token: widget.token,
        chatId: widget.chat.id,
        materialClient: _materialClient,
        quizClient: _quizClient,
        onQuizStartError: (msg) {
          if (!mounted) return;
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
        },
      ),
    );
  }

  /// Şəxsən mənim cavabladığım (`_answeredQuestionIds`) VƏ artıq nəticəsi
  /// gəlmiş (bax `_QuizResultCard` — hamı cavablayıb tur bağlanıb) suallar.
  /// Yalnız local tap-i izləmək kifayət etmirdi: çat yenidən açılanda
  /// (`history`-dən) artıq bağlanmış sual kartı hələ "cavablanmayıb" kimi
  /// göründüyü üçün toxunanda backend-in `AlreadyAnswered` xətası alınırdı.
  Set<int> get _closedQuestionIds => {
        ..._answeredQuestionIds,
        for (final item in _items)
          if (item is QuizResultItem) item.questionId,
      };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.chat.name ?? 'Şəxsi çat'),
        bottom: _connected
            ? null
            : const PreferredSize(
                preferredSize: Size.fromHeight(28),
                child: ColoredBox(
                  color: Colors.orange,
                  child: Center(
                    child: Text(
                      'Bağlantı kəsildi — çıxıb yenidən daxil olun',
                      style: TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ),
                ),
              ),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.all(12),
              itemCount: _items.length,
              itemBuilder: (context, index) => _ChatItemView(
                item: _items[index],
                myUserId: widget.userId,
                answeredQuestionIds: _closedQuestionIds,
                onAnswer: _answerQuestion,
              ),
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              child: Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.attach_file),
                    tooltip: 'Material əlavə et',
                    onPressed: _openMaterialsSheet,
                  ),
                  Expanded(
                    child: TextField(
                      controller: _textController,
                      decoration: const InputDecoration(
                        hintText: 'Mesaj yazın...',
                        border: OutlineInputBorder(),
                        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      ),
                      onSubmitted: (_) => _sendText(),
                    ),
                  ),
                  IconButton(icon: const Icon(Icons.send), onPressed: _sendText),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Bir çat sətrini növünə görə render edir.
class _ChatItemView extends StatelessWidget {
  const _ChatItemView({
    required this.item,
    required this.myUserId,
    required this.answeredQuestionIds,
    required this.onAnswer,
  });

  final ChatItem item;
  final int myUserId;
  final Set<int> answeredQuestionIds;
  final void Function(int questionId, int chosenIndex) onAnswer;

  @override
  Widget build(BuildContext context) {
    final it = item;
    return switch (it) {
      TextChatItem() => _TextBubble(item: it, isMine: it.senderId == myUserId),
      SystemChatItem() => _SystemNotice(item: it),
      QuizQuestionItem() => _QuizQuestionCard(
          item: it,
          answered: answeredQuestionIds.contains(it.questionId),
          onAnswer: onAnswer,
        ),
      QuizResultItem() => _QuizResultCard(item: it),
      QuizFinishedItem() => _QuizFinishedCard(item: it),
    };
  }
}

class _TextBubble extends StatelessWidget {
  const _TextBubble({required this.item, required this.isMine});

  final TextChatItem item;
  final bool isMine;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: isMine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
        decoration: BoxDecoration(
          color: isMine ? const Color(0xFF2F6FED) : const Color(0xFFEFEFEF),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Text(
          item.content,
          style: TextStyle(color: isMine ? Colors.white : Colors.black87),
        ),
      ),
    );
  }
}

class _SystemNotice extends StatelessWidget {
  const _SystemNotice({required this.item});

  final SystemChatItem item;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Center(
        child: Text(
          item.content,
          textAlign: TextAlign.center,
          style: const TextStyle(color: Colors.grey, fontStyle: FontStyle.italic, fontSize: 13),
        ),
      ),
    );
  }
}

class _QuizQuestionCard extends StatelessWidget {
  const _QuizQuestionCard({required this.item, required this.answered, required this.onAnswer});

  final QuizQuestionItem item;
  final bool answered;
  final void Function(int questionId, int chosenIndex) onAnswer;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      color: const Color(0xFFFFF8E1),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.quiz, size: 18),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(item.question, style: const TextStyle(fontWeight: FontWeight.bold)),
                ),
              ],
            ),
            const SizedBox(height: 8),
            for (var i = 0; i < item.options.length; i++)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: OutlinedButton(
                  onPressed: answered ? null : () => onAnswer(item.questionId, i),
                  style: OutlinedButton.styleFrom(alignment: Alignment.centerLeft),
                  child: Text('${String.fromCharCode(65 + i)}) ${item.options[i]}'),
                ),
              ),
            if (answered)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text('Cavabınız qeydə alındı, nəticə gözlənilir...',
                    style: TextStyle(fontSize: 12, color: Colors.grey)),
              ),
          ],
        ),
      ),
    );
  }
}

class _QuizResultCard extends StatelessWidget {
  const _QuizResultCard({required this.item});

  final QuizResultItem item;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      color: const Color(0xFFE8F5E9),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Doğru cavab: ${String.fromCharCode(65 + item.correctIndex)}',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(item.explanation),
            const SizedBox(height: 8),
            for (final a in item.answers)
              Text(
                'İstifadəçi #${a.userId}: ${String.fromCharCode(65 + a.chosenIndex)} ${a.isCorrect ? '✓' : '✗'}',
                style: const TextStyle(fontSize: 12),
              ),
          ],
        ),
      ),
    );
  }
}

class _QuizFinishedCard extends StatelessWidget {
  const _QuizFinishedCard({required this.item});

  final QuizFinishedItem item;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      color: const Color(0xFFE3F2FD),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('🏁 Quiz bitdi!', style: TextStyle(fontWeight: FontWeight.bold)),
            Text('Ümumi sual sayı: ${item.totalQuestions}'),
            const SizedBox(height: 4),
            for (final entry in item.scores.entries)
              Text('İstifadəçi #${entry.key}: ${entry.value} doğru cavab'),
          ],
        ),
      ),
    );
  }
}

/// Material yükləmə + siyahı + "Quiz başlat" bottom sheet-i.
class _MaterialsSheet extends StatefulWidget {
  const _MaterialsSheet({
    required this.token,
    required this.chatId,
    required this.materialClient,
    required this.quizClient,
    required this.onQuizStartError,
  });

  final String token;
  final int chatId;
  final MaterialClient materialClient;
  final QuizClient quizClient;
  final void Function(String message) onQuizStartError;

  @override
  State<_MaterialsSheet> createState() => _MaterialsSheetState();
}

class _MaterialsSheetState extends State<_MaterialsSheet> {
  late Future<List<MaterialInfo>> _materialsFuture;
  bool _uploading = false;
  String? _uploadError;

  @override
  void initState() {
    super.initState();
    _materialsFuture = widget.materialClient.listMaterials(widget.token, widget.chatId);
  }

  void _refresh() {
    setState(() {
      _materialsFuture = widget.materialClient.listMaterials(widget.token, widget.chatId);
    });
  }

  Future<void> _uploadLink() async {
    final controller = TextEditingController();
    final url = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sayt linki əlavə et'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(hintText: 'https://...'),
          autofocus: true,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Ləğv et')),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('Yüklə'),
          ),
        ],
      ),
    );
    if (url == null || url.isEmpty) return;
    await _runUpload(() => widget.materialClient.uploadLink(widget.token, widget.chatId, location: url));
  }

  Future<void> _uploadFile(String kind, List<String>? extensions) async {
    final result = await FilePicker.platform.pickFiles(
      type: extensions == null ? FileType.image : FileType.custom,
      allowedExtensions: extensions,
    );
    final path = result?.files.single.path;
    if (path == null) return;
    await _runUpload(
      () => widget.materialClient.uploadFile(widget.token, widget.chatId, kind: kind, filePath: path),
    );
  }

  Future<void> _runUpload(Future<MaterialInfo> Function() upload) async {
    setState(() {
      _uploading = true;
      _uploadError = null;
    });
    try {
      await upload();
      _refresh();
    } on ApiException catch (e) {
      setState(() => _uploadError = e.message);
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  Future<void> _startQuiz(int materialId) async {
    try {
      await widget.quizClient.startQuiz(widget.token, widget.chatId, materialId: materialId);
      if (mounted) Navigator.pop(context);
    } on ApiException catch (e) {
      widget.onQuizStartError(e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Materiallar', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            children: [
              ActionChip(
                avatar: const Icon(Icons.link, size: 18),
                label: const Text('Link'),
                onPressed: _uploading ? null : _uploadLink,
              ),
              ActionChip(
                avatar: const Icon(Icons.picture_as_pdf, size: 18),
                label: const Text('PDF'),
                onPressed: _uploading ? null : () => _uploadFile('pdf', const ['pdf']),
              ),
              ActionChip(
                avatar: const Icon(Icons.image, size: 18),
                label: const Text('Şəkil'),
                onPressed: _uploading ? null : () => _uploadFile('image', null),
              ),
            ],
          ),
          if (_uploading) ...[
            const SizedBox(height: 12),
            const LinearProgressIndicator(),
          ],
          if (_uploadError != null) ...[
            const SizedBox(height: 8),
            Text(_uploadError!, style: const TextStyle(color: Colors.red)),
          ],
          const SizedBox(height: 16),
          const Divider(),
          SizedBox(
            height: 260,
            child: FutureBuilder<List<MaterialInfo>>(
              future: _materialsFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) {
                  return const Center(child: Text('Materiallar yüklənmədi.'));
                }
                final materials = snapshot.data!;
                if (materials.isEmpty) {
                  return const Center(child: Text('Hələ material yoxdur.'));
                }
                return ListView.builder(
                  itemCount: materials.length,
                  itemBuilder: (context, index) {
                    final m = materials[index];
                    return ListTile(
                      leading: Icon(_iconFor(m.kind)),
                      title: Text(m.label ?? m.location, maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text(_statusLabel(m.status)),
                      trailing: m.status == 'ready'
                          ? FilledButton(
                              onPressed: () => _startQuiz(m.id),
                              child: const Text('Quiz başlat'),
                            )
                          : null,
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  IconData _iconFor(String kind) => switch (kind) {
        'pdf' => Icons.picture_as_pdf,
        'image' => Icons.image,
        _ => Icons.link,
      };

  String _statusLabel(String status) => switch (status) {
        'processing' => 'Emal olunur...',
        'ready' => 'Hazırdır',
        'failed' => 'Uğursuz oldu',
        _ => status,
      };
}
