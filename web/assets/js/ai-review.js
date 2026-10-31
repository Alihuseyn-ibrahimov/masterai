/* AI yoxlama komandasının nəticəsi (gün 10) - `suallar.html` üçün.
 * DOM tələb etmir, Node-da test olunur. Server: `GET/POST
 * /live/question-sets/{id}/review` (bax `pipeline/review_team.py`). */

/** question_id → rəy. Rəy yoxdursa boş xəritə. */
export function reviewByQuestion(review) {
  const map = new Map();
  for (const item of (review && review.items) || []) map.set(item.question_id, item);
  return map;
}

/** Sualın kartındakı nişan. «Yoxlanmadı» QƏSDƏN «qaydasındadır» kimi
 *  göstərilmir: agent cavab verməyibsə, sual təsdiqlənməyib. */
export function verdictBadge(verdict) {
  if (verdict === 'ok') return { className: 'badge badge--success', label: 'AI: qaydasındadır' };
  if (verdict === 'fix') return { className: 'badge badge--warning', label: 'AI: baxın' };
  return { className: 'badge badge--neutral', label: 'AI: yoxlanmadı' };
}

/** Panelin başlıq sətri. */
export function reviewStatusLine(review, total) {
  const status = review ? review.status : 'none';
  if (status === 'processing') return 'AI komandası sualları yoxlayır... Bir neçə dəqiqə çəkə bilər.';
  if (status === 'failed') return `Yoxlama alınmadı: ${review.error || 'naməlum xəta'}`;
  if (status !== 'ready') {
    return 'Üç AI agenti sualları yoxlayır: fakt yoxlayıcı cavabı materialla tutuşdurur, '
      + 'metodist sualın formasına baxır, redaktor problemli suala düzəliş təklif edir.';
  }
  const items = review.items || [];
  const fix = items.filter((i) => i.verdict === 'fix').length;
  const ok = items.filter((i) => i.verdict === 'ok').length;
  const unchecked = Math.max(0, total - fix - ok);
  const parts = [`${ok} sual qaydasındadır`];
  if (fix) parts.push(`${fix} suala baxmaq lazımdır`);
  // Redaktə olunan sualın rəyini server silir - o da bura düşür.
  if (unchecked) parts.push(`${unchecked} sual yoxlanmayıb və ya sonra dəyişdirilib`);
  return `AI yoxlaması: ${parts.join(' · ')}.`;
}

/** Təklif → `PATCH /live/questions/{id}` gövdəsi. Çətinlik dəyişmir. */
export function suggestionPatch(suggestion, difficulty) {
  const body = {
    question: suggestion.question,
    options: suggestion.options.slice(0, 5),
    correct_index: suggestion.correct_index,
    explanation: suggestion.explanation || '',
  };
  if (difficulty) body.difficulty = difficulty;
  return body;
}
