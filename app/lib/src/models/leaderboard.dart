/// `GET /chats/{id}/leaderboard` sətri — yalnız ev tapşırığı xalları
/// (bax Faza 6 dizayn sənədi, "canlı sessiyalar çata bağlı deyil").
class LeaderboardRow {
  final int userId;
  final String displayName;
  final int totalScore;
  final int rank;

  const LeaderboardRow({
    required this.userId,
    required this.displayName,
    required this.totalScore,
    required this.rank,
  });

  factory LeaderboardRow.fromJson(Map<String, dynamic> json) => LeaderboardRow(
        userId: json['user_id'] as int,
        displayName: json['display_name'] as String,
        totalScore: json['total_score'] as int,
        rank: json['rank'] as int,
      );
}
