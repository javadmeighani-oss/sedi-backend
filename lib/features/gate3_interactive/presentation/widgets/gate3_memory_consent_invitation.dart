import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../gate3_localization.dart';

/// Explicit I6 Memory consent invitation — shown only when not granted.
/// Never grants on its own.
class Gate3MemoryConsentInvitation extends StatelessWidget {
  const Gate3MemoryConsentInvitation({
    super.key,
    required this.l10n,
    required this.onGrant,
    required this.onDismiss,
    this.busy = false,
  });

  final Gate3Localization l10n;
  final VoidCallback onGrant;
  final VoidCallback onDismiss;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        color: AppTheme.gate3PaleOliveBackground.withOpacity(0.65),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppTheme.borderInactive.withOpacity(0.28),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            l10n.memoryConsentInvitation,
            style: const TextStyle(
              fontSize: 13,
              height: 1.35,
              color: AppTheme.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              TextButton(
                onPressed: busy ? null : onGrant,
                child: Text(
                  busy ? l10n.memoryConsentBusy : l10n.memoryConsentGrant,
                ),
              ),
              TextButton(
                onPressed: busy ? null : onDismiss,
                child: Text(l10n.memoryConsentNotNow),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
