/* Tələbənin canlı sessiya ekranı - sual, nəticə, bitiş, lövhə.
 *
 * NİYƏ AYRICA MODUL: hazırda yalnız `sessiya.html` işlədir, amma modul
 * QƏSDƏN səhifədən asılı deyil - ekran məntiqi HTML-in içində yazılsa,
 * ikinci ekran lazım olan kimi kopyalanardı. Keçmişdə məhz belə bir bug
 * olub: geri bildirim yalnız hərfi göstərirdi və düzəliş iki ekranda
 * ayrı-ayrı yazılmalı idi. (Faza 4-ə qədər `qosul.html` da bunu
 * işlədirdi; həmin səhifə PIN axını ilə birlikdə silindi.)
 *
 * Modul DOM işlədir, amma elementləri ÖZÜ AXTARMIR - `root` verilir.
 * Saf hesablamalar (`answerFeedback`, `formatCountdown`) ayrı
 * modullardadır və orada test olunur.
 */

import { answerFeedback } from './answer-feedback.js';
import { formatCountdown } from './live-socket.js';

const CARD_IDS = {
  join: 'joinCard',
  wait: 'waitCard',
  question: 'questionCard',
  result: 'resultCard',
  personal: 'personalCard',
  finished: 'finishedCard',
};

export class PlayScreen {
  /** `root` - kartları saxlayan element (adətən `document`).
   *  `onNext` - «Növbəti sual» düyməsi basılanda çağırılır. */
  constructor({ root, onNext }) {
    this.root = root;
    this.onNext = onNext;
    this.currentIndex = 0;
    /* Nəticə kartı düzgün cavabın MƏTNİNİ göstərməlidir, amma server
       yalnız indeks göndərir - variant mətnləri yalnız cari sualdadır. */
    this.currentQuestion = null;
    this.chosenIndex = null;
    this.countdownTimer = null;
    this.remainingSeconds = 0;
    this.onAnswer = () => false;

    this.cards = {};
    for (const [name, id] of Object.entries(CARD_IDS)) {
      const el = root.getElementById(id);
      if (el) this.cards[name] = el;
    }
    this.errorBox = root.getElementById('errorBox');

    const next = root.getElementById('nextBtn');
    if (next) next.addEventListener('click', () => this.onNext());
  }

  show(name) {
    for (const [key, card] of Object.entries(this.cards)) card.hidden = key !== name;
  }

  showError(text) {
    if (!this.errorBox) return;
    this.errorBox.textContent = text;
    this.errorBox.hidden = false;
  }

  clearError() {
    if (this.errorBox) this.errorBox.hidden = true;
  }

  _tick() {
    this.remainingSeconds -= 1;
    this.root.getElementById('countdown').textContent = formatCountdown(this.remainingSeconds);
    if (this.remainingSeconds <= 0 && this.countdownTimer) {
      clearInterval(this.countdownTimer);
      this.countdownTimer = null;
    }
  }

  stopCountdown() {
    if (this.countdownTimer) {
      clearInterval(this.countdownTimer);
      this.countdownTimer = null;
    }
  }

  renderQuestion(data) {
    this.currentIndex = data.index;
    this.currentQuestion = data;
    this.chosenIndex = null;
    this.root.getElementById('questionCounter').textContent =
      `Sual ${data.index + 1}/${data.total}`;
    this.root.getElementById('questionText').textContent = data.question;

    if (typeof data.remaining_seconds === 'number') {
      this.remainingSeconds = Math.max(0, Math.round(data.remaining_seconds));
      this.root.getElementById('countdown').textContent = formatCountdown(this.remainingSeconds);
      if (!this.countdownTimer) this.countdownTimer = setInterval(() => this._tick(), 1000);
    }

    const options = this.root.getElementById('options');
    options.innerHTML = '';
    (data.options || []).forEach((option, index) => {
      const button = document.createElement('button');
      button.className = 'btn btn--secondary btn--block';
      button.type = 'button';
      button.style.justifyContent = 'flex-start';
      button.textContent = `${'ABCDE'[index] || index + 1}. ${option}`;
      button.addEventListener('click', () => {
        // İkiqat toxunuşun qarşısını al - server ikinci cavabı xəta ilə
        // rədd edir və istifadəçi səbəbini anlamır.
        for (const other of options.children) other.disabled = true;
        this.chosenIndex = index;
        if (!this.onAnswer(this.currentIndex, index)) {
          this.showError('Bağlantı hazır deyil - cavab göndərilmədi.');
          this.chosenIndex = null;
          for (const other of options.children) other.disabled = false;
        }
      });
      options.append(button);
    });
    this.show('question');
  }

  renderResult(data) {
    const feedback = answerFeedback({
      options: this.currentQuestion && this.currentQuestion.options,
      correctIndex: data.correct_index,
      chosenIndex: this.chosenIndex,
      isCorrect: data.is_correct,
    });
    const badge = this.root.getElementById('resultBadge');
    badge.className = feedback.badge.className;
    badge.textContent = feedback.badge.label;
    this.root.getElementById('resultQuestion').textContent =
      this.currentQuestion ? this.currentQuestion.question : '';
    const chosen = this.root.getElementById('chosenText');
    chosen.textContent = feedback.chosenLine || '';
    chosen.hidden = !feedback.chosenLine;
    this.root.getElementById('correctText').textContent = feedback.correctLine;
    this.root.getElementById('explanationText').textContent = data.explanation || '';
    this.show('result');
  }

  renderLeaderboard(rows) {
    const container = this.root.getElementById('leaderboard');
    container.innerHTML = '';
    if (!rows || !rows.length) {
      container.innerHTML = '<p class="text-sm text-muted">Nəticə yoxdur.</p>';
      return;
    }
    const list = document.createElement('div');
    list.className = 'stack stack--tight';
    rows.forEach((row, index) => {
      const line = document.createElement('div');
      line.className = 'row row--between';
      const name = document.createElement('span');
      name.className = 'text-sm';
      // Qəsdən textContent - adı istifadəçi yazır.
      name.textContent = `${index + 1}. ${row.display_name || `İştirakçı #${row.participant_id}`}`;
      const score = document.createElement('span');
      score.className = 'text-sm';
      score.textContent = `${row.correct_count ?? row.score ?? 0} düzgün`;
      line.append(name, score);
      list.append(line);
    });
    container.append(list);
  }

  /** Server mesajlarını ekrana çevirir. Tanınmayan tip sükutla atılır. */
  handle(data) {
    if (data.type === 'joined') { this.show('wait'); return; }
    if (data.type === 'question') { this.renderQuestion(data); return; }
    if (data.type === 'result') { this.renderResult(data); return; }
    if (data.type === 'personal_finished') {
      this.root.getElementById('personalScore').textContent =
        `${data.correct_count}/${data.total_questions} düzgün cavab`;
      this.show('personal');
      return;
    }
    if (data.type === 'finished') {
      this.stopCountdown();
      this.renderLeaderboard(data.leaderboard);
      this.show('finished');
      return;
    }
    if (data.type === 'error') this.showError(data.detail || 'Xəta');
  }
}
