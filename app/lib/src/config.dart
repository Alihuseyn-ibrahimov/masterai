/// Backend ünvanları — MasterAI backend-i artıq canlıdır
/// (`masterai/DEPLOY.md`), ayrı staging mühiti yoxdur.
const String kApiBaseUrl = 'https://masterai.prdostu.com';
const String kWsBaseUrl = 'wss://masterai.prdostu.com';

/// `POST /chats/{id}/materials`-dəki backend limiti ilə üst-üstə düşür
/// (`server/app.py`, `MAX_UPLOAD_BYTES`) — client tərəfdə erkən xəbərdarlıq
/// üçün təkrarlanır, əsl yoxlama backend-dədir.
const int kMaxUploadBytes = 20 * 1024 * 1024;
