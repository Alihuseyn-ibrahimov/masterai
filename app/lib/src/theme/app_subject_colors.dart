import 'package:flutter/material.dart';

/// Fənlər üzrə əl ilə seçilmiş aksent rəngləri — Material 3-ün
/// alqoritmik `ColorScheme.fromSeed`-i struktur (fon/kontrast) üçün
/// qalır, bu isə ayrıca "əlavə məlumat qatı"dır (bax vizual dizayn
/// yenilənməsi speci). Açarlar `models/question_set.dart`-dakı
/// `kSubjectLabels`-in AÇARLARI ilə eynidir.
class AppSubjectColors extends ThemeExtension<AppSubjectColors> {
  const AppSubjectColors({
    required this.mentiq,
    required this.informatika,
    required this.dunyagorusu,
    required this.azerbaycanDili,
    required this.qanunvericilik,
    required this.xariciDil,
  });

  final Color mentiq;
  final Color informatika;
  final Color dunyagorusu;
  final Color azerbaycanDili;
  final Color qanunvericilik;
  final Color xariciDil;

  static const light = AppSubjectColors(
    mentiq: Color(0xFF7C4DFF),
    informatika: Color(0xFF00897B),
    dunyagorusu: Color(0xFFEF6C00),
    azerbaycanDili: Color(0xFF2E7D32),
    qanunvericilik: Color(0xFFC62828),
    xariciDil: Color(0xFF1565C0),
  );

  static const dark = AppSubjectColors(
    mentiq: Color(0xFFB39DFF),
    informatika: Color(0xFF64D8CB),
    dunyagorusu: Color(0xFFFFB74D),
    azerbaycanDili: Color(0xFF81C784),
    qanunvericilik: Color(0xFFEF9A9A),
    xariciDil: Color(0xFF90CAF9),
  );

  /// `kSubjectLabels`-in açarı ilə uyğun rəng — naməlum açar üçün
  /// `ColorScheme.primary`-yə geri dönüş çağıranın işidir (bu metod
  /// `BuildContext` almır, ona görə `Theme.of(context).colorScheme.
  /// primary`-ni özü seçə bilmir).
  Color? forSubject(String subjectKey) => switch (subjectKey) {
        'mentiq' => mentiq,
        'informatika' => informatika,
        'dunyagorusu' => dunyagorusu,
        'azerbaycan_dili' => azerbaycanDili,
        'qanunvericilik' => qanunvericilik,
        'xarici_dil' => xariciDil,
        _ => null,
      };

  @override
  AppSubjectColors copyWith({
    Color? mentiq,
    Color? informatika,
    Color? dunyagorusu,
    Color? azerbaycanDili,
    Color? qanunvericilik,
    Color? xariciDil,
  }) {
    return AppSubjectColors(
      mentiq: mentiq ?? this.mentiq,
      informatika: informatika ?? this.informatika,
      dunyagorusu: dunyagorusu ?? this.dunyagorusu,
      azerbaycanDili: azerbaycanDili ?? this.azerbaycanDili,
      qanunvericilik: qanunvericilik ?? this.qanunvericilik,
      xariciDil: xariciDil ?? this.xariciDil,
    );
  }

  @override
  AppSubjectColors lerp(ThemeExtension<AppSubjectColors>? other, double t) {
    if (other is! AppSubjectColors) return this;
    return AppSubjectColors(
      mentiq: Color.lerp(mentiq, other.mentiq, t)!,
      informatika: Color.lerp(informatika, other.informatika, t)!,
      dunyagorusu: Color.lerp(dunyagorusu, other.dunyagorusu, t)!,
      azerbaycanDili: Color.lerp(azerbaycanDili, other.azerbaycanDili, t)!,
      qanunvericilik: Color.lerp(qanunvericilik, other.qanunvericilik, t)!,
      xariciDil: Color.lerp(xariciDil, other.xariciDil, t)!,
    );
  }
}

/// Bir `BuildContext`-dən birbaşa fənn rəngini almaq üçün rahatlıq
/// funksiyası — extension mövcud olmasa (nəzəri cəhətdən, hər zaman
/// `MaterialApp.theme`-ə əlavə olunur) `colorScheme.primary`-yə geri
/// dönür.
Color subjectColor(BuildContext context, String subjectKey) {
  final colors = Theme.of(context).extension<AppSubjectColors>();
  return colors?.forSubject(subjectKey) ?? Theme.of(context).colorScheme.primary;
}

/// `subjectColor`-un fonunda oxunaqlı qalan kontrast rəngi — light
/// temada (tünd/doymuş fənn rəngləri) ağ, dark temada (açıq fənn
/// tonları) demək olar qara.
Color subjectColorForeground(BuildContext context) =>
    Theme.of(context).brightness == Brightness.dark ? Colors.black87 : Colors.white;
