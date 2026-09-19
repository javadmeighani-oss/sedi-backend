import 'package:flutter/material.dart';

import '../../../../core/navigation/app_gate.dart';
import '../../../../core/navigation/app_gate_router.dart';
import '../../../../core/navigation/session_gate_resolver.dart';
import '../../../../core/network/backend_availability.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../services/push/push_service.dart';

/// A1 — Sedi platform intro shown on every app open ("Birth of Sedi").
///
/// Visual animation is independent of auth. Startup session work runs in
/// parallel and is applied only after the intro duration completes.
class IntroPage extends StatefulWidget {
  const IntroPage({super.key});

  /// Approved A1 intro duration (~3 seconds).
  static const Duration kIntroDuration = Duration(milliseconds: 3000);

  /// Canonical horizon / cosmic sunrise background asset.
  static const String kHorizonAsset =
      'assets/images/cosmic_sunrise_background.png';

  /// Final rendered logo size — approved +15% contract (204.24).
  static const double kFinalLogoSize = 204.24;

  @override
  State<IntroPage> createState() => _IntroPageState();
}

class _IntroPageState extends State<IntroPage>
    with SingleTickerProviderStateMixin {
  static const String _logoAsset = 'assets/images/sedi_logo_1024.png';
  static const String _logoFallbackAsset = 'assets/images/sedi_logo_white.png';

  late final AnimationController _masterController;
  late final Animation<double> _scaleAnimation;
  late final Animation<double> _fadeAnimation;

  late final Future<SessionResolveResult> _sessionFuture;
  late final Future<bool> _healthFuture;

  bool _backendAvailable = true;
  bool _showAvailabilityHint = false;

  @override
  void initState() {
    super.initState();

    // Startup work in parallel with animation (does not block first paint).
    _sessionFuture = SessionGateResolver.resolveColdStart();
    _healthFuture = BackendAvailability.probeHealthz();

    _masterController = AnimationController(
      vsync: this,
      duration: IntroPage.kIntroDuration,
    );

    // Uniform linear growth — no pulse, heartbeat, bounce, or breathing loop.
    _scaleAnimation = Tween<double>(begin: 0.28, end: 1.0).animate(
      CurvedAnimation(
        parent: _masterController,
        curve: Curves.linear,
      ),
    );

    _fadeAnimation = Tween<double>(begin: 0.35, end: 1.0).animate(
      CurvedAnimation(
        parent: _masterController,
        curve: const Interval(0.0, 0.28, curve: Curves.easeOut),
      ),
    );

    _masterController.forward();
    _awaitIntroThenRoute();
  }

  Future<void> _awaitIntroThenRoute() async {
    // Animation duration and startup futures already kicked off in initState.
    await Future<void>.delayed(IntroPage.kIntroDuration);
    final session = await _sessionFuture;
    final healthy = await _healthFuture;

    if (!mounted) return;

    setState(() {
      _backendAvailable = healthy;
      _showAvailabilityHint = !healthy ||
          session.status == SessionResolveStatus.backendUnavailable;
    });

    // Brief controlled hint when backend unavailable (does not claim auth).
    if (_showAvailabilityHint) {
      await Future<void>.delayed(const Duration(milliseconds: 450));
      if (!mounted) return;
    }

    await _navigateToNextGate(session);
  }

  Future<void> _navigateToNextGate(SessionResolveResult session) async {
    final nextGate = session.nextGate;

    if (nextGate == SediAppGate.heart) {
      await tryRegisterStoredTokenAfterLogin();
    }

    if (!mounted) return;
    AppGateRouter.transitionFromSplash(
      context,
      nextGate,
      splashPage: build(context),
    );
  }

  @override
  void dispose() {
    _masterController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.introNightSky,
      body: AnimatedBuilder(
        animation: _masterController,
        builder: (context, _) {
          return Stack(
            fit: StackFit.expand,
            children: [
              Positioned.fill(
                child: Image.asset(
                  IntroPage.kHorizonAsset,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) {
                    return const DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            Color(0xFF0A0E14),
                            Color(0xFF1A2332),
                            Color(0xFF3D5A40),
                          ],
                          stops: [0.0, 0.55, 1.0],
                        ),
                      ),
                    );
                  },
                ),
              ),
              SafeArea(
                child: Center(
                  child: Opacity(
                    opacity: _fadeAnimation.value.clamp(0.0, 1.0),
                    child: Transform.scale(
                      scale: _scaleAnimation.value,
                      child: ColorFiltered(
                        colorFilter: const ColorFilter.mode(
                          AppTheme.introLogoEmphasis,
                          BlendMode.srcIn,
                        ),
                        child: Image.asset(
                          _logoAsset,
                          width: IntroPage.kFinalLogoSize,
                          height: IntroPage.kFinalLogoSize,
                          fit: BoxFit.contain,
                          errorBuilder: (context, error, stackTrace) {
                            return Image.asset(
                              _logoFallbackAsset,
                              width: IntroPage.kFinalLogoSize,
                              height: IntroPage.kFinalLogoSize,
                              fit: BoxFit.contain,
                            );
                          },
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              if (_showAvailabilityHint)
                Align(
                  alignment: Alignment.bottomCenter,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(24, 0, 24, 36),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 12,
                      ),
                      color: AppTheme.introOverlaySubtle,
                      child: Text(
                        _backendAvailable
                            ? 'Reconnecting…'
                            : 'Sedi is temporarily unreachable',
                        textAlign: TextAlign.center,
                        style: AppTheme.caption.copyWith(
                          color: AppTheme.introStatusText,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
