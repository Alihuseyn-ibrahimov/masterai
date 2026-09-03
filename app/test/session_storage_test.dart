import 'package:flutter_test/flutter_test.dart';
import 'package:masterai/src/data/session_storage.dart';

void main() {
  test('InMemorySessionStorage: yaz, oxu, təmizlə', () async {
    final storage = InMemorySessionStorage();

    expect(await storage.readToken(), isNull);

    await storage.writeSession(token: 'tok', userId: 7, displayName: 'Əli');
    expect(await storage.readToken(), 'tok');
    expect(await storage.readUserId(), 7);
    expect(await storage.readDisplayName(), 'Əli');

    await storage.clear();
    expect(await storage.readToken(), isNull);
    expect(await storage.readUserId(), isNull);
    expect(await storage.readDisplayName(), isNull);
  });
}
