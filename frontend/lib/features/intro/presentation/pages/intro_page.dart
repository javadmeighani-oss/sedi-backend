import 'package:flutter/material.dart';

import '../../../../core/navigation/app_gate.dart';
import '../../../../core/navigation/app_gate_router.dart';
import '../../../../core/navigation/session_gate_resolver.dart';
import '../../../../services/push/push_service.dart';

/// Gate 1 — Sedi Welcome / Splash (`IntroPage`).
///
/// Cold-start visual entry only. After [kGate1Duration] delegates routing to
/// [SessionGateResolver] → [AppGateRouter] (Gate 2 or Gate 3).
class IntroPage extends StatefulWidget {
  const IntroPage({super.key});

  @override
  State<IntroPage> createState() => _IntroPageState();
}

class _IntroPageState extends State<IntroPage> with SingleTickerProviderStateMixin {
  static const Duration kGate1Duration = Duration(milliseconds: 3000);

  /// Real Sedi logo asset (PNG with transparency). Tinted via [BlendMode.srcIn].
  static const String _logoAsset = 'assets/images/sedi_logo_1024.png';

  static const String _backgroundAsset =
      'assets/images/cosmic_sunrise_background.png';

  /// Final rendered logo width/height on screen (20% larger than prior 148px).
  static const double _finalLogoSize = 177.6;

  /// Gate 1 olive-green palette (multi-step color transition).
  static const Color _colorStart = Color(0xFFFFFFFF);
  static const Color _colorWarmWhite = Color(0xFFEEF3DD);
  static const Color _colorPalePistachio = Color(0xFFD6E9A8);
  static const Color _colorSoftOlive = Color(0xFFB8D77A);
  static const Color _colorFinalOlive = Color(0xFF9BC56B);

  late AnimationController _masterController;
  late Animation<double> _scaleAnimation;
  late Animation<double> _fadeAnimation;
  late Animation<Color?> _colorAnimation;

  @override
  void initState() {
    super.initState();
    _masterController = AnimationController(
      vsync: this,
      duration: kGate1Duration,
    );

    // Uniform linear growth — no pulse / heartbeat rhythm.
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

    // White → Warm White → Pale Pistachio → Soft Olive → Final Olive Green
    _colorAnimation = TweenSequence<Color?>([
      TweenSequenceItem(
        tween: ColorTween(begin: _colorStart, end: _colorWarmWhite),
        weight: 26.67,
      ),
      TweenSequenceItem(
        tween: ColorTween(begin: _colorWarmWhite, end: _colorPalePistachio),
        weight: 26.67,
      ),
      TweenSequenceItem(
        tween: ColorTween(begin: _colorPalePistachio, end: _colorSoftOlive),
        weight: 26.67,
      ),
      TweenSequenceItem(
        tween: ColorTween(begin: _colorSoftOlive, end: _colorFinalOlive),
        weight: 20,
      ),
    ]).animate(_masterController);

    _masterController.forward();

    Future.delayed(kGate1Duration, () {
      if (mounted) {
        _navigateToNextGate();
      }
    });
  }

  @override
  void dispose() {
    _masterController.dispose();
    super.dispose();
  }

  Future<void> _navigateToNextGate() async {
    final nextGate = await SessionGateResolver.resolveAfterSplash();

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
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A0E14),
      body: Stack(
        fit: StackFit.expand,
        children: [
          Positioned.fill(
            child: Image.asset(
              _backgroundAsset,
              fit: BoxFit.cover,
              errorBuilder: (context, error, stackTrace) {
                return Container(
                  decoration: const BoxDecoration(
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
              child: Transform.translate(
                offset: Offset(0, -MediaQuery.of(context).size.height * 0.12),
                child: AnimatedBuilder(
                  animation: _masterController,
                  builder: (context, child) {
                    return Opacity(
                      opacity: _fadeAnimation.value,
                      child: Transform.scale(
                        scale: _scaleAnimation.value,
                        child: child,
                      ),
                    );
                  },
                  child: ColorFiltered(
                    colorFilter: ColorFilter.mode(
                      _colorAnimation.value ?? _colorStart,
                      BlendMode.srcIn,
                    ),
                    child: Image.asset(
                      _logoAsset,
                      width: _finalLogoSize,
                      height: _finalLogoSize,
                      fit: BoxFit.contain,
                      errorBuilder: (context, error, stackTrace) {
                        return Image.asset(
                          'assets/images/sedi_logo_white.png',
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
        ],
      ),
    );
  }
}
