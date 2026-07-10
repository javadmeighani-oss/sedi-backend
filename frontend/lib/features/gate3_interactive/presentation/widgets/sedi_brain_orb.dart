import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/utils/brand_name.dart';
import '../../../chat/presentation/widgets/sedi_ring_anim.dart';
import '../../models/gate3_interaction_state.dart';

class SediBrainOrb extends StatelessWidget {
  final Gate3InteractionState state;
  final String lang;

  /// 15% smaller than the previous 150px orb.
  static const double _size = 127.5;

  const SediBrainOrb({
    super.key,
    required this.state,
    required this.lang,
  });

  @override
  Widget build(BuildContext context) {
    final isThinking = state == Gate3InteractionState.thinking;
    final logoSize = _size * 0.78;
    // Inner brand text ~20% larger than the prior SediHeader ratio (0.24 → 0.288).
    final brandFontSize = logoSize * 0.288;
    final brand = sediBrandName(lang);

    return SizedBox(
      width: _size,
      height: _size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // Subtle halo
          Container(
            width: _size * 1.06,
            height: _size * 1.06,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF8A9A6B).withOpacity(0.14),
                  blurRadius: 22,
                  spreadRadius: 1,
                ),
              ],
            ),
          ),
          SediRingAnim(
            active: isThinking,
            size: _size,
            thickness: 2.2,
          ),
          Container(
            width: logoSize,
            height: logoSize,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFFF7F5EF),
              border: Border.all(
                color: const Color(0xFFE4E8DC).withOpacity(0.9),
                width: 1,
              ),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x10000000),
                  blurRadius: 14,
                  offset: Offset(0, 5),
                ),
              ],
            ),
            child: Center(
              child: Image.asset(
                'assets/images/sedi_logo_1024.png',
                fit: BoxFit.contain,
                width: logoSize * 0.7,
                height: logoSize * 0.7,
                errorBuilder: (_, __, ___) {
                  return Text(
                    '$brand.',
                    style: TextStyle(
                      fontSize: brandFontSize,
                      fontWeight: FontWeight.w800,
                      color: AppTheme.primaryBlack,
                      letterSpacing: -0.5,
                    ),
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}
