import 'package:flutter/material.dart';

import '../gate3_localization.dart';
import '../pages/gate3_profile_page.dart';
import 'gate3_main_icon_button.dart';

/// A3 top row: Profile | Lifestyle | Gadgets | Smart Notifications.
/// Health lives inside Lifestyle (no separate top Health icon).
class Gate3MainIconRow extends StatelessWidget {
  final VoidCallback onLifestyle;
  final VoidCallback onGadgets;
  final VoidCallback onNotifications;
  final String lang;

  const Gate3MainIconRow({
    super.key,
    required this.onLifestyle,
    required this.onGadgets,
    required this.onNotifications,
    required this.lang,
  });

  Gate3Localization get _l10n => Gate3Localization(lang);

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: [
        Gate3MainIconButton(
          icon: Icons.person_outline,
          label: l10n.profileTitle,
          plainIcon: true,
          onTap: () {
            Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const Gate3ProfilePage(),
              ),
            );
          },
        ),
        Gate3MainIconButton(
          icon: Icons.self_improvement_outlined,
          label: l10n.lifestyle,
          onTap: onLifestyle,
        ),
        Gate3MainIconButton(
          icon: Icons.devices_other_outlined,
          label: l10n.gadgets,
          onTap: onGadgets,
        ),
        Gate3MainIconButton(
          icon: Icons.notifications_none_outlined,
          label: l10n.notifications,
          plainIcon: true,
          onTap: onNotifications,
        ),
      ],
    );
  }
}
