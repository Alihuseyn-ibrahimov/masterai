/* Zəif mövzu analizi (Faza 2 PR 2, 2026-11-03) - DOM-suz məntiq.
 *
 * `GET /me/topics` artıq güclü/zəif siyahılarını AYRILMIŞ qaytarır
 * (bax `server/topic_stats.py::split_strong_weak`) - burada yalnız
 * göstərmə məntiqi var, hesablama yoxdur.
 */

/** Göstəriləcək bir şey varmı? Hər iki siyahı boşdursa (hələ kifayət
 *  qədər cavab yoxdur) blok mənasızdır. */
export function hasTopicStats(data) {
  return Boolean(data && ((data.strong && data.strong.length) || (data.weak && data.weak.length)));
}

/** «65% düzgün (3 cavab)» */
export function topicLine(stat) {
  return `${stat.percent}% düzgün (${stat.total} cavab)`;
}

export function renderTopicStats(data, doc = document) {
  const wrap = doc.createElement('div');
  wrap.className = 'stack';

  function section(title, stats, badgeClass) {
    if (!stats.length) return;
    const heading = doc.createElement('p');
    heading.className = 'text-sm text-muted';
    heading.textContent = title;
    wrap.append(heading);
    for (const stat of stats) {
      const line = doc.createElement('div');
      line.className = 'row row--between';
      const left = doc.createElement('span');
      left.className = `badge ${badgeClass}`;
      left.textContent = stat.topic;
      const right = doc.createElement('span');
      right.className = 'text-sm';
      right.textContent = topicLine(stat);
      line.append(left, right);
      wrap.append(line);
    }
  }

  // Qırmızı/yaşıl variant rəngi kimi İŞLƏDİLMİR (bax quiz UX dərsi) -
  // burada da eyni qayda: «zəif» siqnalı xəbərdarlıq rəngi, «güclü»
  // brend yaşılının doymuş variantıdır.
  section('Zəif mövzular - bunlara daha çox vaxt ayırın', data.weak || [], 'badge--warning');
  section('Güclü mövzular', data.strong || [], 'badge--success');
  return wrap;
}
