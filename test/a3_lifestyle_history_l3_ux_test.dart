import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/lifestyle/presentation/lifestyle_l10n.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  test('L3 History is a read-only white archive without Talk to Sedi', () {
    final src = _read(
      'lib/features/lifestyle/presentation/pages/lifestyle_history_page.dart',
    );
    expect(src.contains('A3DestinationSurface.canvas'), isTrue);
    expect(src.contains('gate3PaleOliveBackground'), isFalse);
    expect(src.contains('A3DestinationCard'), isTrue);
    expect(src.contains('/memory/history'), isTrue);
    expect(src.contains('/memory/period-summary'), isTrue);
    expect(src.contains("'user_id'"), isFalse);
    expect(src.contains('daily'), isTrue);
    expect(src.contains('weekly'), isTrue);
    expect(src.contains('monthly'), isTrue);
    expect(src.contains('yearly'), isTrue);
    expect(src.contains('openLifestyleChat'), isFalse);
    expect(src.contains('lifestyle_page.dart'), isFalse);
    expect(src.contains('l10n.openChat'), isFalse);
    expect(src.contains('historyExplain'), isTrue);

    final explainEn = LifestyleL10n('en').historyExplain.toLowerCase();
    expect(explainEn.contains('ask sedi'), isFalse);
    expect(explainEn.contains('in chat'), isFalse);
    expect(explainEn.contains('read-only'), isTrue);
    expect(LifestyleL10n('fa').historyExplain.contains('چت'), isFalse);
    expect(LifestyleL10n('ar').historyExplain.contains('الدردشة'), isFalse);
  });
}
