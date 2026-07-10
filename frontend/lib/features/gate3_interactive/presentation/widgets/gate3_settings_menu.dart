import 'package:flutter/material.dart';

import '../../../../core/auth/auth_helper.dart';
import '../../../../core/theme/app_theme.dart';
import '../gate3_localization.dart';

/// Minimal settings entry for Gate 3 (profile placeholder + logout).
class Gate3SettingsMenu extends StatelessWidget {
  final String lang;

  const Gate3SettingsMenu({
    super.key,
    required this.lang,
  });

  Gate3Localization get _l10n => Gate3Localization(lang);

  void _showMenu(BuildContext context) {
    final l10n = _l10n;
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
                    _showProfilePlaceholder(context);
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

  void _showProfilePlaceholder(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(_l10n.editProfile),
        content: Text(_l10n.profileSettingsPlaceholder),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(_l10n.close),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkResponse(
        onTap: () => _showMenu(context),
        radius: 22,
        child: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.55),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: AppTheme.borderInactive.withOpacity(0.25),
            ),
          ),
          child: const Icon(
            Icons.settings_outlined,
            size: 20,
            color: AppTheme.primaryBlack,
          ),
        ),
      ),
    );
  }
}
