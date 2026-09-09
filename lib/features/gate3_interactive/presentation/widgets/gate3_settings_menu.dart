import 'package:flutter/material.dart';

import '../../../../core/auth/auth_helper.dart';
import '../../../../core/theme/app_theme.dart';
import '../gate3_localization.dart';

/// Gate 3 settings sheet (profile placeholder + logout).
class Gate3SettingsMenu {
  Gate3SettingsMenu._();

  static void show(BuildContext context, String lang) {
    final l10n = Gate3Localization(lang);
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppTheme.gate3PaleOliveBackground,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  l10n.settings,
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                    color: AppTheme.textPrimary,
                  ),
                ),
                const SizedBox(height: 12),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.person_outline_rounded),
                  title: Text(l10n.editProfile),
                  onTap: () {
                    Navigator.of(ctx).pop();
                    _showProfilePlaceholder(context, l10n);
                  },
                ),
                const Divider(height: 1),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.logout_rounded),
                  title: Text(l10n.logout),
                  onTap: () async {
                    Navigator.of(ctx).pop();
                    await AuthHelper.performLogout(context: context);
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  static void _showProfilePlaceholder(
    BuildContext context,
    Gate3Localization l10n,
  ) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.editProfile),
        content: Text(l10n.profileSettingsPlaceholder),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(l10n.close),
          ),
        ],
      ),
    );
  }
}
