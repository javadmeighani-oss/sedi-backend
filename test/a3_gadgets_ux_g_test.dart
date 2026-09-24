import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  test('Gadgets destination uses structured white cards without joined debug facts',
      () {
    final src = _read(
      'lib/features/devices/presentation/pages/devices_page.dart',
    );
    expect(src.contains('A3DestinationSurface.canvas'), isTrue);
    expect(src.contains('gate3PaleOliveBackground'), isFalse);
    expect(src.contains('A3DestinationCard'), isTrue);
    expect(src.contains('selfDevices'), isTrue);
    expect(src.contains('otherDevices'), isTrue);
    expect(src.contains('unclassifiedDevices'), isTrue);
    expect(src.contains('manualDisconnect'), isTrue);
    expect(src.contains('l10n.connect'), isTrue);
    expect(src.contains('facts.join'), isFalse);
    expect(src.contains('join(\' · \')'), isFalse);
    expect(src.contains('SediBlePermissions.request'), isTrue);
    expect(src.contains('toIso8601String'), isFalse);
    expect(src.contains('dangerRed'), isFalse);
  });
}
