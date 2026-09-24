import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  test('Profile groups user info into a white card without new editable fields',
      () {
    final src = _read(
      'lib/features/gate3_interactive/presentation/pages/gate3_profile_page.dart',
    );
    expect(src.contains('A3DestinationSurface.canvas'), isTrue);
    expect(src.contains('A3DestinationCard'), isTrue);
    expect(src.contains('userInformationSection'), isTrue);
    expect(src.contains('userSummarySection'), isTrue);
    expect(src.contains('AuthHelper.performLogout'), isTrue);
    expect(src.contains('_phoneCard'), isTrue);
    expect(src.contains('TextDirection.ltr'), isTrue);
    expect(src.contains('A2PhoneE164'), isTrue);
    expect(src.contains('Gate2OtpInput'), isTrue);
    expect(src.contains('/auth/me/profile-summary'), isTrue);
    expect(src.contains('fetchMe'), isTrue);
    expect(src.contains('requestPhoneChangeOtp'), isTrue);
    expect(src.contains('verifyPhoneChangeOtp'), isTrue);
    expect(src.contains('canonicalProfileSummaryText'), isTrue);

    final infoIdx = src.indexOf('userInformationSection');
    final phoneIdx = src.indexOf('Widget _phoneCard');
    final summaryIdx = src.indexOf('userSummarySection');
    final logoutIdx = src.indexOf('AuthHelper.performLogout');
    expect(infoIdx, greaterThan(0));
    expect(phoneIdx, greaterThan(infoIdx));
    expect(logoutIdx, greaterThan(summaryIdx));
  });
}
