import 'sedi_audio_visualizer_geometry.dart';

/// Responsive vertical budget for the Gate 3 interactive page.
class Gate3VerticalLayout {
  Gate3VerticalLayout._();

  /// Icon row intrinsic height (44 icon + 6 gap + ~22 label).
  static const double iconRowHeight = 72;

  /// Top icon padding and spacer below the row.
  static const double topSectionSpacing = 12;

  static const double belowOrbSpacing = 8;

  static const double chatPanelOuterPadding = 8;

  /// Minimum scrollable message viewport inside the chat panel.
  static const double minMessageViewportHeight = 96;

  /// Composer card margin, field, and toolbar minimum.
  static const double composerMinimumHeight = 108;

  static double reservedBelowVisualizerHeight({
    double belowOrbSpacing = Gate3VerticalLayout.belowOrbSpacing,
  }) {
    return belowOrbSpacing +
        chatPanelOuterPadding +
        minMessageViewportHeight +
        composerMinimumHeight;
  }

  static double reservedAboveChatPanelHeight({
    double belowOrbSpacing = Gate3VerticalLayout.belowOrbSpacing,
  }) {
    return iconRowHeight +
        topSectionSpacing +
        reservedBelowVisualizerHeight(belowOrbSpacing: belowOrbSpacing);
  }

  /// Fixed visualizer canvas height — never shrinks with keyboard or viewport.
  static double resolveVisualizerCanvasHeight({
    required double orbBodyRadius,
    double belowOrbSpacing = Gate3VerticalLayout.belowOrbSpacing,
  }) {
    return SediAudioVisualizerGeometry.preferredCanvasHeight(orbBodyRadius);
  }
}
