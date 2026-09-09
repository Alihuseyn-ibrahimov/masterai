/* Backend ünvanları — TƏK mənbə.
 *
 * Faza 9-da API ayrıca subdomenə köçəcək (`api.masterai.prdostu.com`);
 * o zaman YALNIZ bu fayl dəyişəcək. Hazırda backend hələ kök
 * subdomendədir.
 *
 * `localhost`-dan açılanda (fayla iki dəfə klik və ya `python -m
 * http.server`) canlı backend işlədilir — ayrıca staging mühiti yoxdur
 * (bax `masterai/DEPLOY.md`). */

export const API_BASE_URL = 'https://masterai.prdostu.com';
export const WS_BASE_URL = 'wss://masterai.prdostu.com';

/** `POST /chats/{id}/materials`-dəki backend limiti (server/app.py,
 *  MAX_UPLOAD_BYTES) — client tərəfdə erkən xəbərdarlıq üçün
 *  təkrarlanır, əsl yoxlama backend-dədir. */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
