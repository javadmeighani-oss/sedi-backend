import 'package:flutter/material.dart';

import '../../models/gate3_interaction_state.dart';
import 'sedi_audio_visualizer_geometry.dart';
import 'sedi_audio_visualizer_painter.dart';
import 'sedi_brand_lockup.dart';
import 'sedi_orb_texture_painter.dart';

/// Living Sedi brain orb — white eye surface with spectrum visualizer.
class SediBrainOrb extends StatefulWidget {
  final Gate3InteractionState state;

  /// Optional visualizer canvas height. Defaults to the geometry-derived
  /// preferred height for full spectrum paint at the approved orb size.
  final double? canvasHeight;

  /// Fixed Latin brand mark inside the orb (never localized).
  static const String brandLabel = SediBrandLockup.label;

  /// Pre-scale Gate 3 orb allocation from commit `5033433`.
  static const double baselineSize = 136;

  /// 7% reduction applied to the committed orb body system dimensions.
  static const double scaleFactor = 0.93;

  /// Legacy coupled canvas/orb extent retained for diameter math only.
  static const double legacyCoupledExtent = baselineSize * scaleFactor;

  static const double orbBodyRatio = 0.72;

  /// Approved 10% reduction from commit `628b310` normal non-keyboard size.
  static const double visualizerSizeScale =
      SediAudioVisualizerGeometry.visualizerSizeScale;

  static double get orbDiameter =>
      legacyCoupledExtent * orbBodyRatio * visualizerSizeScale;

  static double get orbBodyRadius => orbDiameter / 2;

  /// Official wordmark height ratio inside the orb (5% smaller than 0.272).
  static const double brandHeightRatio = 0.2584;

  /// Fixed visualizer slot height — identical with keyboard open or closed.
  static double get fixedVisualizerCanvasHeight => preferredVisualizerCanvasHeight;

  /// Previous coupled visualizer allocation (126.48).
  static const double legacyVisualizerCanvasHeight = legacyCoupledExtent;

  static double get preferredVisualizerCanvasHeight =>
      SediAudioVisualizerGeometry.preferredCanvasHeight(orbBodyRadius);

  static double get minimumVisualizerCanvasHeight =>
      SediAudioVisualizerGeometry.minimumCanvasHeight(orbBodyRadius);

  /// Legacy coupled extent used only for approved orb diameter math.
  static const double size = legacyCoupledExtent;

  const SediBrainOrb({
    super.key,
    required this.state,
    this.canvasHeight,
  });

  @override
  State<SediBrainOrb> createState() => _SediBrainOrbState();
}

class _SediBrainOrbState extends State<SediBrainOrb>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  double _horizontalEnergy = SediAudioVisualizerPainter.targetHorizontalEnergy(
    Gate3InteractionState.idle,
  );
  double _horizontalPhase = 0;
  double _horizontalPhaseSpeed =
      SediAudioVisualizerPainter.horizontalPhaseSpeed(
    Gate3InteractionState.idle,
  );
  double _lastControllerValue = 0;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 10),
    )..addListener(_tickVisualState)
      ..repeat();
  }

  @override
  void didUpdateWidget(covariant SediBrainOrb oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.state != widget.state) {
      _tickVisualState();
    }
  }

  void _tickVisualState() {
    final advanced = SediAudioVisualizerPainter.advanceHorizontalPhase(
      phase: _horizontalPhase,
      speed: _horizontalPhaseSpeed,
      lastControllerValue: _lastControllerValue,
      controllerValue: _controller.value,
      state: widget.state,
    );
    _horizontalPhase = advanced.phase;
    _horizontalPhaseSpeed = advanced.speed;
    _lastControllerValue = advanced.lastControllerValue;

    final target =
        SediAudioVisualizerPainter.targetHorizontalEnergy(widget.state);
    final nextEnergy = _horizontalEnergy + (target - _horizontalEnergy) * 0.12;
    if ((nextEnergy - _horizontalEnergy).abs() > 0.0005) {
      setState(() => _horizontalEnergy = nextEnergy);
    }
  }

  @override
  void dispose() {
    _controller.removeListener(_tickVisualState);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final orbDiameter = SediBrainOrb.orbDiameter;
    final orbBodyRadius = SediBrainOrb.orbBodyRadius;
    final brandHeight = orbDiameter * SediBrainOrb.brandHeightRatio;
    final visualizerCanvasHeight =
        widget.canvasHeight ?? SediBrainOrb.fixedVisualizerCanvasHeight;

    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth.isFinite
            ? constraints.maxWidth
            : SediBrainOrb.preferredVisualizerCanvasHeight;
        final orbCenter = Offset(width / 2, visualizerCanvasHeight / 2);
        final layout = SediAudioVisualizerPainter.resolveLayout(
          width: width,
          containerHeight: visualizerCanvasHeight,
          orbBodyRadius: orbBodyRadius,
        );

        return SizedBox(
          width: width,
          height: visualizerCanvasHeight,
          child: AnimatedBuilder(
            animation: _controller,
            builder: (context, child) {
              final circularPhase = SediAudioVisualizerPainter.deriveCircularPhase(
                _controller.value,
              );
              return CustomPaint(
                painter: SediAudioVisualizerPainter(
                  circularPhase: circularPhase,
                  horizontalPhase: _horizontalPhase,
                  horizontalEnergy: _horizontalEnergy,
                  state: widget.state,
                  orbCenter: orbCenter,
                  orbBodyRadius: orbBodyRadius,
                  spectrumRadius: layout.spectrumRadius,
                  barExtensionFactor: layout.barExtensionFactor,
                  glowPaintRadiusBeyondSpectrum:
                      layout.glowPaintRadiusBeyondSpectrum,
                  glowShaderExtraBeyondBarExtension:
                      layout.glowShaderExtraBeyondBarExtension,
                ),
                child: Center(child: child),
              );
            },
            child: Container(
              width: orbDiameter,
              height: orbDiameter,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white,
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFFD8DFC8).withOpacity(0.45),
                    blurRadius: 16,
                    spreadRadius: 0.5,
                  ),
                  BoxShadow(
                    color: const Color(0xFF8A9A6B).withOpacity(0.1),
                    blurRadius: 22,
                    offset: const Offset(0, 5),
                  ),
                ],
                border: Border.all(
                  color: const Color(0xFFE6E9DC).withOpacity(0.85),
                ),
              ),
              child: Stack(
                alignment: Alignment.center,
                children: [
                  ClipOval(
                    child: CustomPaint(
                      size: Size(orbDiameter, orbDiameter),
                      painter: const SediOrbTexturePainter(),
                    ),
                  ),
                  SediBrandLockup(height: brandHeight),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
