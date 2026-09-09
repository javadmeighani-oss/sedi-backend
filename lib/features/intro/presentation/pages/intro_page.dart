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

  @override
  State<IntroPage> createState() => _IntroPageState();
}

class _IntroPageState extends State<IntroPage>
    with SingleTickerProviderStateMixin {
  /// Intended intro duration ≈ 2.5 seconds (frames 1 → 3).
  static const Duration kIntroDuration = Duration(milliseconds: 2500);

  static const String _logoAsset = 'assets/images/sedi_logo_1024.png';
  static const String _logoFallbackAsset = 'assets/images/sedi_logo_white.png';
  static const double _finalLogoSize = 204.24;

  late final AnimationController _masterController;
  late final Animation<double> _scaleAnimation;
  late final Animation<double> _fadeAnimation;
  late final Animation<double> _riseAnimation;
  late final Animation<double> _glowAnimation;

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
      duration: kIntroDuration,
    );

    // Phase 1 (0–700ms): tiny / faint near horizon
    // Phase 2 (700–1600ms): emerge upward, scale + opacity
    // Phase 3 (1600–2500ms): stable born presentation
    _scaleAnimation = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween(begin: 0.12, end: 0.22)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 28,
      ),
      TweenSequenceItem(
        tween: Tween(begin: 0.22, end: 0.85)
            .chain(CurveTween(curve: Curves.easeOutCubic)),
        weight: 36,
      ),
      TweenSequenceItem(
        tween: Tween(begin: 0.85, end: 1.0)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 36,
      ),
    ]).animate(_masterController);

    _fadeAnimation = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween(begin: 0.08, end: 0.28)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 28,
      ),
      TweenSequenceItem(
        tween: Tween(begin: 0.28, end: 0.92)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 36,
      ),
      TweenSequenceItem(
        tween: Tween(begin: 0.92, end: 1.0)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 36,
      ),
    ]).animate(_masterController);

    // Rise from horizon: positive dy early → settle near center-upper.
    _riseAnimation = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween(begin: 0.22, end: 0.18)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 28,
      ),
      TweenSequenceItem(
        tween: Tween(begin: 0.18, end: -0.06)
            .chain(CurveTween(curve: Curves.easeOutCubic)),
        weight: 36,
      ),
      TweenSequenceItem(
        tween: Tween(begin: -0.06, end: -0.10)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 36,
      ),
    ]).animate(_masterController);

    _glowAnimation = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween(begin: 0.25, end: 0.45)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 28,
      ),
      TweenSequenceItem(
        tween: Tween(begin: 0.45, end: 0.85)
            .chain(CurveTween(curve: Curves.easeInOut)),
        weight: 36,
      ),
      TweenSequenceItem(
        tween: Tween(begin: 0.85, end: 0.70)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 36,
      ),
    ]).animate(_masterController);

    _masterController.forward();
    _awaitIntroThenRoute();
  }

  Future<void> _awaitIntroThenRoute() async {
    final results = await Future.wait<Object>([
      Future<void>.delayed(kIntroDuration),
      _sessionFuture,
      _healthFuture,
    ]);

    if (!mounted) return;

    final session = results[1] as SessionResolveResult;
    final healthy = results[2] as bool;

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
    final height = MediaQuery.of(context).size.height;

    return Scaffold(
      backgroundColor: AppTheme.introNightSky,
      body: AnimatedBuilder(
        animation: _masterController,
        builder: (context, _) {
          return Stack(
            fit: StackFit.expand,
            children: [
              // Night sky → horizon glow atmosphere (AppTheme only).
              DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      AppTheme.introNightSky,
                      Color.lerp(
                        AppTheme.introAtmosphere,
                        AppTheme.introHorizonGlow,
                        _glowAnimation.value * 0.55,
                      )!,
                      Color.lerp(
                        AppTheme.introHorizonGlow,
                        AppTheme.introEmergenceAccent,
                        _glowAnimation.value * 0.35,
                      )!,
                    ],
                    stops: const [0.0, 0.58, 1.0],
                  ),
                ),
              ),
              // Soft horizon bloom.
              Align(
                alignment: Alignment.bottomCenter,
                child: Opacity(
                  opacity: _glowAnimation.value.clamp(0.0, 1.0),
                  child: Container(
                    height: height * 0.42,
                    decoration: BoxDecoration(
                      gradient: RadialGradient(
                        center: const Alignment(0, 0.85),
                        radius: 1.15,
                        colors: [
                          AppTheme.introEmergenceAccent
                              .withOpacity(0.35 * _glowAnimation.value),
                          AppTheme.introHorizonGlow
                              .withOpacity(0.18 * _glowAnimation.value),
                          AppTheme.introNightSky.withOpacity(0.0),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              // Sedi emergence from horizon.
              SafeArea(
                child: Align(
                  alignment: Alignment.center,
                  child: Transform.translate(
                    offset: Offset(0, height * _riseAnimation.value),
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
                            width: _finalLogoSize,
                            height: _finalLogoSize,
                            fit: BoxFit.contain,
                            errorBuilder: (context, error, stackTrace) {
                              return Image.asset(
                                _logoFallbackAsset,
                                width: _finalLogoSize,
                                height: _finalLogoSize,
                                fit: BoxFit.contain,
                              );
                            },
                          ),
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
