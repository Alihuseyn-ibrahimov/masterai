/* Sinif liderlik lövhəsinin sətirləri - saf funksiya.
 *
 * NİYƏ AYRICA MODUL: hesablama DOM-dan asılı deyil və `node --test` ilə
 * birbaşa yoxlanır. Server onsuz da sıralanmış siyahı qaytarır, burada
 * isə GÖSTƏRİŞ qərarları verilir (öz sətrini vurğula, komponent mətni).
 */

/** Bir sətrin göstəriş formasını qurur. */
export function leaderboardRow(row, currentUserId) {
  const homework = Number(row.homework_score) || 0;
  const live = Number(row.live_score) || 0;
  return {
    rank: row.rank,
    name: row.display_name,
    total: Number(row.total_score) || 0,
    // Komponentlər HƏMİŞƏ göstərilir, sıfır olsa da: tələbə hansı
    // sahədə geridə qaldığını görməlidir, boş yer isə bunu gizlədər.
    breakdown: `Ev tapşırığı ${homework} · Canlı sessiya ${live}`,
    isMe: row.user_id === currentUserId,
  };
}

/** Bütün siyahı. Server sıralamasına TOXUNMUR - sıra və `rank` orada
 *  hesablanır, burada təkrar sıralamaq iki mənbə yaradardı. */
export function leaderboardRows(rows, currentUserId) {
  return (rows || []).map((row) => leaderboardRow(row, currentUserId));
}

/** Boş lövhə mətni. Üzv yoxdursa və xal yoxdursa fərqli səbəblərdir. */
export function emptyLeaderboardText(rows) {
  if (!rows || !rows.length) {
    return 'Bu çatda hələ tələbə yoxdur.';
  }
  if (rows.every((row) => (Number(row.total_score) || 0) === 0)) {
    return 'Hələ xal yoxdur - ilk ev tapşırığı və ya canlı sessiyadan sonra görünəcək.';
  }
  return '';
}
