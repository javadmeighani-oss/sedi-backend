import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/auth/auth_refresh_service.dart';

void main() {
  setUp(AuthRefreshService.debugReset);
  tearDown(AuthRefreshService.debugReset);

  test('concurrent callers await the same in-flight refresh', () async {
    var performs = 0;
    AuthRefreshService.debugPerformOverride = () async {
      performs += 1;
      await Future<void>.delayed(const Duration(milliseconds: 40));
      return AuthRefreshOutcome.success;
    };

    final results = await Future.wait<Object>([
      AuthRefreshService.refreshOnce(),
      AuthRefreshService.refreshOnce(),
      AuthRefreshService.tryRefresh(),
    ]);

    expect(performs, 1);
    expect(results[0], AuthRefreshOutcome.success);
    expect(results[1], AuthRefreshOutcome.success);
    expect(results[2], isTrue);
  });

  test('transient timeout is not treated as success or invalid session',
      () async {
    AuthRefreshService.debugPerformOverride = () async {
      await Future<void>.delayed(const Duration(milliseconds: 5));
      return AuthRefreshOutcome.transientFailure;
    };

    final first = AuthRefreshService.refreshOnce();
    final second = AuthRefreshService.refreshOnce();
    expect(await first, AuthRefreshOutcome.transientFailure);
    expect(await second, AuthRefreshOutcome.transientFailure);
    expect(await AuthRefreshService.tryRefresh(), isFalse);
  });

  test('authoritative invalid session is distinct from transient failure',
      () async {
    AuthRefreshService.debugPerformOverride =
        () async => AuthRefreshOutcome.invalidSession;
    expect(
      await AuthRefreshService.refreshOnce(),
      AuthRefreshOutcome.invalidSession,
    );
    expect(await AuthRefreshService.tryRefresh(), isFalse);
  });
}
