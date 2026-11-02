/* Açılış səhifəsinin canlı nümunələri (2026-11-02).
 *
 * NİYƏ: hero-dakı sual statik şəkil idi - ziyarətçi məhsulun ƏSAS anını
 * (tələbə cavablayır, sinif irəliləyir, seriya artır) görmürdü. İndi o an
 * özü oynayır. Hamısı saytın REAL komponentləri ilə (`.option`, seriya
 * nişanı), video və kitabxana YOXDUR.
 *
 * Qaydalar:
 * - HTML-dəki statik vəziyyət tam və doğrudur: JS işləməsə və ya
 *   «hərəkəti azalt» seçilibsə səhifə əvvəlki kimi görünür.
 * - Ekrandan çıxanda və ya tab gizlənəndə dövrə dayanır (batareya).
 * - Məntiq (söz sırası, addım cədvəli, sayğac) saf funksiyalardır və
 *   Node-da test olunur; DOM hissəsi `start*` funksiyalarındadır.
 */

/** Başlıqda dəyişən söz: «Dərs keçin, ___ AI hazırlasın». İlk söz
 *  HTML-dəki statik sözdür (SEO və ekran oxuyucu onu görür). */
export const HEADLINE_WORDS = ['qalanını', 'konspekti', 'quizi', 'davamiyyəti'];

/** Növbəti söz (dövrəvi). */
export function nextWord(words, current) {
  const index = words.indexOf(current);
  return words[(index + 1) % words.length];
}

/** Hero sualları: ikisi də yuxarıdakı DƏRS PARÇASINDAN çıxır - nümunə
 *  material ilə sual arasındakı əlaqəni göstərməlidir. */
export const DEMO_QUESTIONS = [
  {
    number: 3,
    prompt: 'Dövlət qulluqçusuna aşağıdakılardan hansı qəti qadağandır?',
    options: ['Elmi və pedaqoji fəaliyyət', 'Sahibkarlıq fəaliyyəti ilə məşğul olmaq', 'Yaradıcılıq fəaliyyəti'],
    correct: 1,
    explain: 'İzah: qanun sahibkarlıq fəaliyyətini birbaşa qadağan edir, elmi və pedaqoji fəaliyyəti isə istisna kimi saxlayır.',
  },
  {
    number: 4,
    prompt: 'Hansı fəaliyyət sahibkarlıq qadağasına aid DEYİL?',
    options: ['Pedaqoji fəaliyyət', 'Ticarət şirkəti açmaq', 'Mənfəət üçün xidmət göstərmək'],
    correct: 0,
    explain: 'İzah: elmi, pedaqoji və yaradıcılıq fəaliyyəti qadağaya aid deyil - dərsdə məhz bu istisna vurğulanıb.',
  },
];

/** Sinifdəki tələbə sayı (nümunə, statistik iddia DEYİL). */
export const CLASS_SIZE = 18;

/**
 * Bir sualın zaman cədvəli, millisaniyə ilə (sualın başlanğıcından).
 * `answered` - həmin anda neçə tələbənin cavabladığı.
 * Ardıcıllıq: sual çıxır → sinif cavablamağa başlayır → «tələbə» variantı
 * seçir (rəngsiz «gözlənilir») → düzgün açılır, seriya artır, izah
 * görünür → bir az dayanır → növbəti sual.
 */
export function demoTimeline(classSize = CLASS_SIZE) {
  return [
    { at: 0, phase: 'ask', answered: 0 },
    { at: 900, phase: 'ask', answered: Math.round(classSize * 0.25) },
    { at: 1700, phase: 'chosen', answered: Math.round(classSize * 0.5) },
    { at: 2600, phase: 'correct', answered: Math.round(classSize * 0.78) },
    { at: 3400, phase: 'correct', answered: classSize - 2 },
    { at: 6800, phase: 'next', answered: classSize - 2 },
  ];
}

/** «Nə qədər cavablayıb» mətni. */
export function answeredText(answered, classSize = CLASS_SIZE) {
  return `${answered} / ${classSize} tələbə cavabladı`;
}

/** Seriya nişanının mətni. */
export function streakText(streak) {
  return `${streak} ardıcıl düzgün`;
}

/* ---------------- DOM ---------------- */

function prefersReducedMotion(win) {
  return Boolean(win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

/** Element görünəndə `onVisible(true)`, çıxanda `false`. */
function watchVisibility(win, element, onVisible) {
  if (!('IntersectionObserver' in win)) {
    onVisible(true);
    return;
  }
  new win.IntersectionObserver((entries) => {
    for (const entry of entries) onVisible(entry.isIntersecting);
  }, { threshold: 0.25 }).observe(element);
}

export function startHeadlineRotator(doc = document, win = window) {
  const word = doc.querySelector('[data-rotator]');
  if (!word || prefersReducedMotion(win)) return;
  // Sözlərin uzunluğu fərqlidir: «davamiyyəti» başlığı bir sətir artırır və
  // altdakı hər şey tullanırdı (render-də ölçüldü, 390 en: 76 ↔ 113 px).
  // Başlığa ən uzun sözün hündürlüyü qədər yer saxlanır.
  const title = word.closest('h1') || word.parentElement;
  function reserveHeight() {
    const current = word.textContent;
    title.style.minHeight = '';
    let tallest = 0;
    for (const candidate of HEADLINE_WORDS) {
      word.textContent = candidate;
      tallest = Math.max(tallest, title.getBoundingClientRect().height);
    }
    word.textContent = current;
    title.style.minHeight = `${Math.ceil(tallest)}px`;
  }
  reserveHeight();
  let resizeTimer = null;
  win.addEventListener('resize', () => {
    win.clearTimeout(resizeTimer);
    resizeTimer = win.setTimeout(reserveHeight, 150);
  });
  let visible = true;
  watchVisibility(win, word, (v) => { visible = v; });
  win.setInterval(() => {
    if (!visible || doc.hidden) return;
    word.classList.add('rotator__word--out');
    win.setTimeout(() => {
      word.textContent = nextWord(HEADLINE_WORDS, word.textContent.trim());
      word.classList.remove('rotator__word--out');
    }, 220);
  }, 2600);
}

export function startQuestionDemo(doc = document, win = window) {
  const card = doc.querySelector('[data-demo]');
  if (!card || prefersReducedMotion(win)) return;
  const $ = (selector) => card.querySelector(selector);
  const options = [...card.querySelectorAll('.option')];
  // Bir «düzgün» işarəsi (i-check) düzgün varianta köçürülür. `hidden` atributu burada
  // İŞLƏMİR: `.option__mark` öz `display`-i ilə onu üstələyir (render-də
  // tutuldu - işarə köhnə variantda qalırdı).
  const mark = card.querySelector('.option__mark');
  const timeline = demoTimeline();
  let streak = Number($('[data-demo-streak]').dataset.demoStreak) || 3;
  let questionIndex = 0;
  let step = 0;
  let timer = null;
  let running = false;

  function render(question, moment) {
    $('[data-demo-number]').textContent = `Sual ${question.number}/10`;
    $('[data-demo-prompt]').textContent = question.prompt;
    options.forEach((option, i) => {
      option.querySelector('.option__text').textContent = question.options[i];
      const isCorrect = i === question.correct;
      option.classList.toggle('option--chosen', moment.phase === 'chosen' && isCorrect);
      option.classList.toggle('option--correct', moment.phase === 'correct' && isCorrect);
      if (mark && moment.phase === 'correct' && isCorrect) option.append(mark);
    });
    if (mark && moment.phase !== 'correct') mark.remove();
    // `visibility`, `hidden` yox: izah yeri saxlanır, kart hündürlüyü
    // hər dövrədə tullanmır.
    $('[data-demo-explain]').style.visibility = moment.phase === 'correct' ? '' : 'hidden';
    $('[data-demo-explain]').textContent = question.explain;
    $('[data-demo-answered]').textContent = answeredText(moment.answered);
    $('[data-demo-bar]').style.setProperty('--progress', `${Math.round(moment.answered / CLASS_SIZE * 100)}%`);
  }

  function tick() {
    if (!running) return;
    const moment = timeline[step];
    if (moment.phase === 'next') {
      questionIndex = (questionIndex + 1) % DEMO_QUESTIONS.length;
      step = 0;
      timer = win.setTimeout(tick, 0);
      return;
    }
    if (moment.phase === 'correct' && timeline[step - 1].phase === 'chosen') {
      // Seriya yalnız düzgün açılan anda artır; 9-dan sonra yenidən 3.
      streak = streak >= 9 ? 3 : streak + 1;
      const badge = $('[data-demo-streak]');
      badge.querySelector('span').textContent = streakText(streak);
      badge.classList.remove('trace__badge--pop');
      void badge.offsetWidth;  // animasiyanı yenidən başlat
      badge.classList.add('trace__badge--pop');
    }
    render(DEMO_QUESTIONS[questionIndex], moment);
    const next = timeline[step + 1];
    step += 1;
    timer = win.setTimeout(tick, next.at - moment.at);
  }

  function setRunning(on) {
    if (on === running) return;
    running = on;
    win.clearTimeout(timer);
    if (on) tick();
  }

  // Statik vəziyyətdən (düzgün cavab açıq) ilk dövrəyə bir az gözləyib keçir:
  // ziyarətçi əvvəlcə tam sualı görsün.
  let visible = false;
  watchVisibility(win, card, (v) => {
    visible = v;
    setRunning(visible && !doc.hidden);
  });
  doc.addEventListener('visibilitychange', () => setRunning(visible && !doc.hidden));
  step = timeline.length - 2;  // «correct» dayanmasından başla
}

/** Proyektor nümunəsində adlar bir-bir «qoşulur» - BİR dəfə, bölmə ilk
 *  dəfə görünəndə. Statik HTML-də hamısı artıq görünür. */
export function startShowcaseJoin(doc = document, win = window) {
  const list = doc.querySelector('[data-join-names]');
  const count = doc.querySelector('[data-join-count]');
  if (!list || !count || prefersReducedMotion(win) || !('IntersectionObserver' in win)) return;
  const names = [...list.children];
  names.forEach((li) => { li.hidden = true; });
  count.textContent = '0';
  let started = false;
  const observer = new win.IntersectionObserver((entries) => {
    if (started || !entries.some((e) => e.isIntersecting)) return;
    started = true;
    observer.disconnect();
    names.forEach((li, i) => {
      win.setTimeout(() => {
        li.hidden = false;
        li.classList.add('showcase__name--pop');
        count.textContent = String(i + 1);
      }, 350 + i * 420);
    });
  }, { threshold: 0.4 });
  observer.observe(list);
}

export function startLandingDemos(doc = document, win = window) {
  startHeadlineRotator(doc, win);
  startQuestionDemo(doc, win);
  startShowcaseJoin(doc, win);
}
