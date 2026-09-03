/// Bütün REST client-lərin ortaq xəta tipi. `message` istifadəçiyə birbaşa
/// göstərilə bilən Azərbaycanca mətndir (dildostu-nun `AuthException`
/// naxışı — səssiz udma, ekran tutub göstərsin).
class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

const kNetworkErrorMessage = 'Bağlantı xətası — internetini yoxla və yenidən cəhd et.';
