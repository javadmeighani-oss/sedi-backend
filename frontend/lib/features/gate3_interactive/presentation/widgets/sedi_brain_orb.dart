import 'package:flutter/material.dart';

import '../../../chat/presentation/widgets/sedi_header.dart';
import '../../models/gate3_interaction_state.dart';

class SediBrainOrb extends StatelessWidget {
  final Gate3InteractionState state;

  const SediBrainOrb({
    super.key,
    required this.state,
  });

  @override
  Widget build(BuildContext context) {
    final isThinking = state == Gate3InteractionState.thinking;

    // V1: idle-ready default; ring animation only when thinking.
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SediHeader(
          isThinking: isThinking,
          isAlert: false,
          size: 150,
        ),
        const SizedBox(height: 10),
        const Text(
          'صدی آماده شنیدن است',
          textDirection: TextDirection.rtl,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: Color(0xFF55624A),
            height: 1.2,
          ),
        ),
      ],
    );
  }
}

