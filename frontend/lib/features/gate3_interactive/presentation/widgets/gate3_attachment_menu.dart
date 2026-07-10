import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../gate3_localization.dart';

/// Attachment entry sheet for Gate 3 composer (UI placeholder only).
class Gate3AttachmentMenu {
  Gate3AttachmentMenu._();

  static Future<void> show(BuildContext context, String lang) async {
    final l10n = Gate3Localization(lang);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppTheme.gate3PaleOliveBackground,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                _AttachmentMenuItem(
                  icon: Icons.camera_alt_outlined,
                  label: l10n.camera,
                  onTap: () => _onPlaceholderTap(context, l10n),
                ),
                const SizedBox(height: 8),
                _AttachmentMenuItem(
                  icon: Icons.photo_outlined,
                  label: l10n.photos,
                  onTap: () => _onPlaceholderTap(context, l10n),
                ),
                const SizedBox(height: 8),
                _AttachmentMenuItem(
                  icon: Icons.attach_file_outlined,
                  label: l10n.files,
                  onTap: () => _onPlaceholderTap(context, l10n),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  static void _onPlaceholderTap(BuildContext context, Gate3Localization l10n) {
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(l10n.attachmentComingSoon),
        behavior: SnackBarBehavior.floating,
        margin: const EdgeInsets.only(bottom: 96, left: 16, right: 16),
      ),
    );
  }
}

class _AttachmentMenuItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _AttachmentMenuItem({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withOpacity(0.72),
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFFF0F2EA),
                ),
                child: Icon(icon, size: 22, color: AppTheme.primaryBlack),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: AppTheme.textPrimary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
