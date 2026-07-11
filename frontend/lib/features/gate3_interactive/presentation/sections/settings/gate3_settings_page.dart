import 'package:flutter/material.dart';

import '../../../../../core/auth/auth_helper.dart';
import '../../../../../core/theme/app_theme.dart';
import '../../gate3_localization.dart';
import '../../gate3_sections_localization.dart';
import '../../widgets/gate3_section_scaffold.dart';
import 'gate3_close_contacts_page.dart';

class Gate3SettingsPage extends StatelessWidget {
  final String lang;

  const Gate3SettingsPage({super.key, required this.lang});

  @override
  Widget build(BuildContext context) {
    final gate3 = Gate3Localization(lang);
    final l10n = Gate3SectionsLocalization(lang);

    return Gate3SectionScaffold(
      lang: lang,
      title: l10n.settingsTitle,
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          _SettingsTile(
            icon: Icons.people_outline_rounded,
            title: l10n.closeContactsTitle,
            onTap: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => Gate3CloseContactsPage(lang: lang),
                ),
              );
            },
          ),
          _SettingsTile(
            icon: Icons.person_outline_rounded,
            title: gate3.editProfile,
            onTap: () {
              showDialog<void>(
                context: context,
                builder: (ctx) => AlertDialog(
                  title: Text(gate3.editProfile),
                  content: Text(gate3.profileSettingsPlaceholder),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.of(ctx).pop(),
                      child: Text(l10n.close),
                    ),
                  ],
                ),
              );
            },
          ),
          const Divider(height: 24),
          _SettingsTile(
            icon: Icons.logout_rounded,
            title: gate3.logout,
            destructive: true,
            onTap: () => AuthHelper.performLogout(context: context),
          ),
        ],
      ),
    );
  }
}

class _SettingsTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final VoidCallback onTap;
  final bool destructive;

  const _SettingsTile({
    required this.icon,
    required this.title,
    required this.onTap,
    this.destructive = false,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withOpacity(0.88),
      borderRadius: BorderRadius.circular(16),
      child: ListTile(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        leading: Icon(
          icon,
          color: destructive ? AppTheme.dangerRed : AppTheme.gate2ButtonOlive,
        ),
        title: Text(
          title,
          style: TextStyle(
            color: destructive ? AppTheme.dangerRed : AppTheme.textPrimary,
            fontWeight: FontWeight.w600,
          ),
        ),
        trailing: const Icon(Icons.chevron_right_rounded),
        onTap: onTap,
      ),
    );
  }
}
