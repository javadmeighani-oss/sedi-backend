import 'package:flutter/material.dart';

import '../gate3_localization.dart';
import 'gate3_main_icon_button.dart';
import 'gate3_settings_menu.dart';

/// Primary Gate 3 navigation row: Settings, Health Care, Lifestyle, Gadgets.
///
/// Notifications (Gate 4) and History (Lifestyle sub-section) are intentionally
/// not shown here.
class Gate3MainIconRow extends StatelessWidget {
  final VoidCallback onHealthCare;
  final VoidCallback onLifestyle;
  final VoidCallback onGadgets;
  final String lang;

  const Gate3MainIconRow({
    super.key,
    required this.onHealthCare,
    required this.onLifestyle,
    required this.onGadgets,
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
          icon: Icons.settings_outlined,
          label: l10n.settings,
          plainIcon: true,
          onTap: () => Gate3SettingsMenu.show(context, lang),
        ),
        Gate3MainIconButton(
          icon: Icons.favorite_border,
          label: l10n.healthCare,
          onTap: onHealthCare,
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
      ],
    );
  }
}
