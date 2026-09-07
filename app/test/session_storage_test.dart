import 'package:flutter_test/flutter_test.dart';
import 'package:masterai/src/data/session_storage.dart';

void main() {
  test('InMemorySessionStorage: yaz, oxu, təmizlə', () async {
    final storage = InMemorySessionStorage();

    expect(await storage.readToken(), isNull);

    await storage.writeSession(token: 'tok', userId: 7, displayName: 'Əli', isTeacher: true);
    expect(await storage.readToken(), 'tok');
    expect(await storage.readUserId(), 7);
    expect(await storage.readDisplayName(), 'Əli');
    expect(await storage.readIsTeacher(), true);

    await storage.clear();
    expect(await storage.readToken(), isNull);
    expect(await storage.readUserId(), isNull);
    expect(await storage.readDisplayName(), isNull);
    expect(await storage.readIsTeacher(), false);
  });
}
