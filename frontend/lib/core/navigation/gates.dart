/// Barrel export for the Sedi 3-gate frontend architecture layer.
///
/// ```text
/// Gate 1 (splash)  → IntroPage
/// Gate 2 (auth)    → OtpLoginPage
/// Gate 3 (heart)   → ChatPage
/// ```
///
/// Decision flow: [SessionGateResolver] → [AppGateRouter]
library;

export 'app_gate.dart';
export 'app_gate_router.dart';
export 'session_gate_resolver.dart';
