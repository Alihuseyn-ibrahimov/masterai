/* Kurs Kassası səhifəsinin (kassa.html) saf köməkçiləri - DOM yoxdur,
 * ona görə node testləri ilə yoxlanır. */

const MONTHS = ['Yan', 'Fev', 'Mar', 'Apr', 'May', 'İyn', 'İyl', 'Avq', 'Sen', 'Okt', 'Noy', 'Dek'];

/** 1234 -> «1 234 AZN»; mənfi qalıq mənfi işarə ilə qalır. */
export function azn(amount) {
  const value = Number(amount) || 0;
  const digits = String(Math.abs(Math.round(value))).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return `${value < 0 ? '-' : ''}${digits} AZN`;
}

/** 0.8333 -> «83%»; gözlənilən gəlir yoxdursa «-». */
export function percent(rate) {
  return rate === null || rate === undefined ? '-' : `${Math.round(rate * 100)}%`;
}

/** «2026-11» -> «Noy 2026». */
export function monthLabel(month) {
  const [year, mon] = String(month).split('-');
  const name = MONTHS[Number(mon) - 1];
  return name ? `${name} ${year}` : String(month);
}

/** Borclunun qısa təsviri: neçə gün gecikib, neçə aydır ödəmir. */
export function debtLabel(debtor) {
  const parts = [`${debtor.days_overdue} gün gecikir`];
  if (debtor.paid_amount > 0) parts.unshift(`qismən: ${azn(debtor.paid_amount)} ödəyib`);
  // Server ardıcıllığı 12 ayda kəsir: 12 = «ən azı 12», «heç ödəməyib» demək olmaz.
  if (debtor.unpaid_months >= 12) {
    parts.push('12+ aydır ödəmir');
    return parts.join(' · ');
  }
  if (debtor.unpaid_months > 1) parts.push(`${debtor.unpaid_months} aydır ödəmir`);
  if (debtor.last_paid_month) parts.push(`son ödəniş: ${monthLabel(debtor.last_paid_month)}`);
  else parts.push('heç ödəməyib');
  return parts.join(' · ');
}

/** Zolağın doluluğu 0..1; gözlənilən sıfırdırsa 0 (bölmə xətası yox). */
export function trendShare(collected, expected) {
  if (!expected) return 0;
  return Math.max(0, Math.min(1, collected / expected));
}

const SOURCES = { llm: 'AI oxudu', rules: 'qaydalarla oxundu' };

/** Oxunmuş qəbzin bir sətirlik xülasəsi: «120 AZN · 03.11.2026 · Aysel · kart *4417». */
export function receiptLine(receipt) {
  const amount = Number(receipt.amount);
  const parts = [Number.isInteger(amount) ? azn(amount) : `${amount.toFixed(2)} AZN`];
  if (receipt.date) parts.push(receipt.date.split('-').reverse().join('.'));
  if (receipt.student) parts.push(receipt.student);
  if (receipt.payer) parts.push(`ödəyən: ${receipt.payer}`);
  if (receipt.card_last4) parts.push(`kart *${receipt.card_last4}`);
  if (SOURCES[receipt.source]) parts.push(SOURCES[receipt.source]);
  return parts.join(' · ');
}

/** Qəbzdəki məbləğ şagirdin aylıq məbləği ilə üst-üstə düşmürsə xəbərdarlıq, yoxsa ''. */
export function amountWarning(receipt, candidate) {
  if (!candidate || candidate.monthly_amount == null) return '';
  if (Math.abs(receipt.amount - candidate.monthly_amount) < 0.005) return '';
  return `Qəbzdə ${receipt.amount} AZN, aylıq məbləğ ${candidate.monthly_amount} AZN. «Ödədi» aylıq məbləği yazır.`;
}
