/// `badge_type` açarından Azərbaycan mətninə/emoji-yə xəritə — server
/// yalnız texniki açarı (ASCII, `kSubjectLabels`-in eyni naxışı)
/// qaytarır, göstərilən mətn client-dədir.
class BadgeMeta {
  const BadgeMeta({required this.emoji, required this.title, required this.description});

  final String emoji;
  final String title;
  final String description;
}

const Map<String, BadgeMeta> kBadgeMeta = {
  'ilk_addim': BadgeMeta(
    emoji: '🎯',
    title: 'İlk addım',
    description: 'İlk canlı sessiyanızı və ya ev tapşırığınızı tamamladınız',
  ),
  'yuz_faiz': BadgeMeta(
    emoji: '💯',
    title: '100% dəqiqlik',
    description: 'Bir sınaqda bütün sualları düzgün cavablandırdınız',
  ),
  'fenn_ustasi': BadgeMeta(
    emoji: '🏆',
    title: 'Fənn ustası',
    description: 'Eyni fənndə 5 ev tapşırığı tamamladınız',
  ),
  'suretli_eqli': BadgeMeta(
    emoji: '⚡',
    title: 'Sürətli əqli',
    description: 'Ev tapşırığını 3 dəqiqədən az müddətdə bitirdiniz',
  ),
  'silsile_5': BadgeMeta(
    emoji: '🔥',
    title: 'Silsilə 5',
    description: '5 fərqli gündə fəal oldunuz',
  ),
};

class BadgeInfo {
  final String badgeType;
  final bool earned;
  final String? earnedAt;

  const BadgeInfo({required this.badgeType, required this.earned, required this.earnedAt});

  BadgeMeta get meta =>
      kBadgeMeta[badgeType] ?? BadgeMeta(emoji: '🏅', title: badgeType, description: '');

  factory BadgeInfo.fromJson(Map<String, dynamic> json) => BadgeInfo(
        badgeType: json['badge_type'] as String,
        earned: json['earned'] as bool,
        earnedAt: json['earned_at'] as String?,
      );
}
