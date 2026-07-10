import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Subtle internal neural / leaf-like texture inside the Sedi orb.
class SediOrbTexturePainter extends CustomPainter {
  final double phase;

  const SediOrbTexturePainter({required this.phase});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;

    canvas.save();
    canvas.clipPath(
      Path()..addOval(Rect.fromCircle(center: center, radius: radius)),
    );

    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    const branchCount = 6;
    for (var i = 0; i < branchCount; i++) {
      final baseAngle = (i / branchCount) * math.pi * 2 + phase * math.pi * 2;
      final path = Path();
      var point = center;
      path.moveTo(point.dx, point.dy);

      for (var step = 0; step < 4; step++) {
        final t = (step + 1) / 4;
        final wave = math.sin(phase * math.pi * 4 + step * 1.2 + i) * 0.08;
        final dist = radius * (0.18 + t * 0.55);
        final angle = baseAngle + wave;
        point = center + Offset(math.cos(angle) * dist, math.sin(angle) * dist);
        final ctrl = center +
            Offset(
              math.cos(angle - 0.25) * dist * 0.65,
              math.sin(angle - 0.25) * dist * 0.65,
            );
        path.quadraticBezierTo(ctrl.dx, ctrl.dy, point.dx, point.dy);
      }

      paint
        ..color = const Color(0xFF8A9A6B).withOpacity(0.07 + (i % 2) * 0.02)
        ..strokeWidth = 1.1;
      canvas.drawPath(path, paint);
    }

    // Soft leaf veins
    for (var i = 0; i < 3; i++) {
      final angle = phase * math.pi + i * (math.pi * 2 / 3);
      final end = center + Offset(math.cos(angle) * radius * 0.42, math.sin(angle) * radius * 0.42);
      paint
        ..color = const Color(0xFFB8C4A0).withOpacity(0.12)
        ..strokeWidth = 1.4;
      canvas.drawLine(center, end, paint);
    }

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant SediOrbTexturePainter oldDelegate) =>
      oldDelegate.phase != phase;
}
