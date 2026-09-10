/* Sual yoxlama ekranının SAF məntiqi (DOM-suz) - `suallar.html`.
 *
 * Ekranın məqsədi: müəllim 30 sualı bərabər gözdən keçirə bilmir, ona
 * görə praktikada heç birini oxumur. `GET /live/question-sets/{id}/quality`
 * hansı sualın şübhəli olduğunu deyir; burada həmin cavab ekran sırasına
 * çevrilir.
 *
 * DİQQƏT: audit cavabın DOĞRU olduğunu demir (bax `pipeline/quality.py`
 * modul qeydi) - yalnız şübhə əlamətlərini sayır. Tapıntısı olmayan sual
 * "təsdiqlənmiş" DEYİL, sadəcə statistik əlamət verməyib.
 */

export const SOURCE_ORDER = 'source';
export const REVIEW_ORDER = 'review';

/** Tapıntıları sual nömrəsinə görə qruplaşdırır.
 *  Dəstin BÜTÜNÜNƏ aid tapıntılar (`question_number === null`) daxil
 *  EDİLMİR - onları konkret sual kartına yapışdırsaq müəllim səhv sualı
 *  düzəltməyə başlayar. */
export function findingsByQuestion(findings) {
  const byQuestion = new Map();
  for (const finding of findings || []) {
    if (finding.question_number == null) continue;
    const list = byQuestion.get(finding.question_number) || [];
    list.push(finding);
    byQuestion.set(finding.question_number, list);
  }
  return byQuestion;
}

/** Yalnız dəstin bütününə aid tapıntılar (məs. mövqe əyriliyi). */
export function setWideFindings(findings) {
  return (findings || []).filter((finding) => finding.question_number == null);
}

/** Şübhəli SUAL sayı (tapıntı sayı yox): bir sualda üç tapıntı olsa da
 *  müəllim bir sual oxuyacaq. */
export function suspiciousCount(findings) {
  return findingsByQuestion(findings).size;
}

/**
 * Ekranda göstəriləcək 0-bazlı indekslərin sırası.
 *
 * `reviewOrder` backend-dən 1-bazlı gəlir. İki qoruyucu var, çünki
 * audit cavabı ilə sual siyahısı ARASINDA vaxt fərqi ola bilər (sual
 * silinib, audit köhnədir):
 *   - siyahıda olmayan nömrə atılır,
 *   - audit sırasına düşməyən sual sona əlavə olunur - heç bir sual
 *     ekrandan YOX OLMAMALIDIR.
 */
export function orderedIndexes(count, reviewOrder, mode) {
  const source = Array.from({ length: count }, (unused, index) => index);
  if (mode !== REVIEW_ORDER) return source;

  const seen = new Set();
  const ordered = [];
  for (const number of reviewOrder || []) {
    const index = number - 1;
    if (index < 0 || index >= count || seen.has(index)) continue;
    seen.add(index);
    ordered.push(index);
  }
  for (const index of source) if (!seen.has(index)) ordered.push(index);
  return ordered;
}

const SEVERITY = {
  yuksek: { className: 'badge badge--danger', label: 'Yüksək' },
  orta: { className: 'badge badge--warning', label: 'Orta' },
  asagi: { className: 'badge badge--neutral', label: 'Aşağı' },
};

/** Naməlum səviyyə rəngsiz qalmır - backend yeni səviyyə əlavə etsə
 *  nişan yox olmamalıdır. */
export function severityBadge(severity) {
  return SEVERITY[severity] || { className: 'badge badge--neutral', label: 'Qeyd' };
}
