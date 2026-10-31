/* Dərs səhifəsinin (dersim.html) tab-ları - saf funksiyalar.
 *
 * NİYƏ: auditdə (2026-10-31) dərs səhifəsi uzun bir sütun idi
 * (konspekt, quiz, qeyd alt-alta), tutor isə başlıqdakı ikinci dərəcəli
 * düymə idi. Telefonda quizə çatmaq üçün konspekti keçib aşağı sürüşmək
 * lazım idi. İndi hər bölmə bir tab-dır və səhifə ən faydalı tab-la açılır.
 *
 * «Mətn» (dərsin transkripti) YALNIZ müəllimdədir: server onu yalnız
 * müəllimə verir (`/live/lessons/{id}/transcript`), tələbə konspekti görür.
 */

export const TABS = [
  { key: 'summary', label: 'Konspekt', icon: 'notes' },
  { key: 'quiz', label: 'Quiz', icon: 'bolt' },
  { key: 'note', label: 'Qeydim', icon: 'pencil' },
  { key: 'tutor', label: 'Tutor', icon: 'message' },
  { key: 'text', label: 'Mətn', icon: 'microphone', teacherOnly: true },
];

/** Rola görə görünən tab-lar (sıra sabitdir). */
export function visibleTabs(isTeacher) {
  return TABS.filter((tab) => isTeacher || !tab.teacherOnly);
}

/** Bitirilməmiş quiz sayı - tab-ın nişanında göstərilir. */
export function openQuizCount(assignments) {
  return (assignments || []).filter((a) => a && a.status !== 'tamamlanıb').length;
}

/**
 * Səhifə açılanda seçiləcək tab.
 *   1. Linkdə keçərli `#tab` varsa - o (yeniləmə və paylaşılan link).
 *   2. Tələbənin bitirmədiyi quiz varsa - Quiz (növbəti addım odur).
 *   3. Konspekt verilibsə - Konspekt.
 *   4. Müəllim üçün - Mətn (dərsdən sonra ilk baxdığı yer).
 *   5. Əks halda - Qeydim (dərs zamanı yazmaq üçün).
 */
export function initialTab({ hash, isTeacher, summary, assignments }) {
  const keys = visibleTabs(isTeacher).map((tab) => tab.key);
  const fromHash = String(hash || '').replace(/^#/, '');
  if (keys.includes(fromHash)) return fromHash;
  if (!isTeacher && openQuizCount(assignments) > 0) return 'quiz';
  if (summary) return 'summary';
  if (isTeacher) return 'text';
  return 'note';
}

/**
 * Klaviatura ilə tab dəyişmə (WAI-ARIA tabs naxışı): sağ/sol ox
 * dövri keçir, Home/End - ilk/son. Başqa düymədə `null`.
 */
export function nextTabKey(keys, current, key) {
  const index = keys.indexOf(current);
  if (index < 0 || !keys.length) return null;
  if (key === 'ArrowRight') return keys[(index + 1) % keys.length];
  if (key === 'ArrowLeft') return keys[(index - 1 + keys.length) % keys.length];
  if (key === 'Home') return keys[0];
  if (key === 'End') return keys[keys.length - 1];
  return null;
}

/**
 * Başlıqdakı əsas düymə. Dərs otağı YALNIZ canlı onlayn dərsdədir:
 * auditdə planlaşdırılmış dərsdə «Dərs otağı» düyməsi görünürdü və
 * boş otağa aparırdı, bitmiş dərsdə isə otaq onsuz da boşdur.
 */
export function lessonPrimaryAction(lesson) {
  if (!lesson || lesson.mode !== 'online' || lesson.status !== 'live') return null;
  return { label: 'Dərsə qoşul', href: `dars.html?id=${encodeURIComponent(lesson.id)}` };
}

/** Başlıq altındakı vəziyyət cümləsi (rol və dərs vəziyyətinə görə).
 *  `shared` - tələbəyə konspekt və ya quiz artıq verilibmi. */
export function lessonStatusNote(lesson, isTeacher, shared = false) {
  if (!lesson) return '';
  if (lesson.status === 'scheduled') {
    return lesson.mode === 'online'
      ? 'Dərs başlayanda burada «Dərsə qoşul» düyməsi görünəcək.'
      : 'Sinif dərsidir. Davamiyyət dərs zamanı lövhədəki QR kodla qeyd olunur.';
  }
  if (lesson.status === 'ended') {
    return isTeacher
      ? 'Dərs bitib. Mətndən quiz və konspekt hazırlayıb «Dərslər» səhifəsindən tələbələrə göndərin.'
      : shared
        ? 'Dərs bitib. Təkrar üçün konspekt və quiz aşağıdadır.'
        : 'Dərs bitib. Konspekt və quiz müəllim paylaşanda burada görünür.';
  }
  return '';
}
