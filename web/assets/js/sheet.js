/* Vərəq (bottom sheet) - formanı siyahının üstündən açan pəncərə.
 *
 * NİYƏ: auditdə (2026-10-31) «Dərslər», «Ev tapşırıqları» və «Çatlar»
 * səhifələri FORMA ilə açılırdı - müəllim öz dərslərini, tapşırıqlarını
 * görmək üçün hər dəfə formanı keçib aşağı sürüşürdü, tələbə isə
 * «yeni çat yarat» formasını əsas hərəkət kimi görürdü. İndi siyahı
 * yuxarıdadır, forma başlıqdakı düymə ilə açılır.
 *
 * İSTİSNA: «Quiz yarat» (muellim.html) formanı yuxarıda AÇIQ saxlayır -
 * bunu istifadəçi real pilotdan sonra özü seçib (bax səhifədəki şərh).
 *
 * Yerli <dialog> + showModal(): fokus vərəqin içində qalır, Esc bağlayır,
 * arxa plan klikə bağlanır - kitabxana lazım deyil. Telefonda ekranın
 * altından çıxır, kompüterdə ortada pəncərədir (CSS: `.sheet`).
 */

/** Link `#key` ilə gəlibsə (məs. «Bu gün»dəki «Dərs planla») açılacaq
 *  vərəqin açarı; tanınmayan və ya boş hash - `null`. */
export function sheetKeyFromHash(hash, keys) {
  const key = String(hash || '').replace(/^#/, '');
  return (keys || []).includes(key) ? key : null;
}

/**
 * Bir <dialog class="sheet">-i qoşur.
 *   openers  - vərəqi açan düymələr
 *   onOpen   - açılanda (məs. ilk sahəyə fokus, köhnə xətanı gizlət)
 * Qaytarır: { open(), close() }.
 */
export function bindSheet(dialog, { openers = [], onOpen } = {}) {
  function open() {
    if (dialog.open) return;
    dialog.showModal();
    if (onOpen) onOpen();
  }
  function close() {
    if (dialog.open) dialog.close();
  }
  for (const button of openers) button.addEventListener('click', open);
  for (const button of dialog.querySelectorAll('[data-sheet-close]')) {
    button.addEventListener('click', close);
  }
  // Arxa plana (pərdəyə) klik: hədəf dialogun özüdür, içindəki element yox.
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) close();
  });
  // Hash ilə açılıbsa bağlananda silinir: yeniləmə vərəqi təkrar açmasın.
  dialog.addEventListener('close', () => {
    if (location.hash) history.replaceState(null, '', `${location.pathname}${location.search}`);
  });
  return { open, close };
}
