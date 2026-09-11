import 'package:flutter/material.dart';

import '../../../../core/health_subject/sedi_health_subject_controller.dart';
import '../../../../core/theme/app_theme.dart';
import '../gate3_localization.dart';

/// Minimal active-subject chip + picker (no redesign).
class Gate3SubjectSelector extends StatelessWidget {
  final Gate3Localization l10n;

  const Gate3SubjectSelector({super.key, required this.l10n});

  @override
  Widget build(BuildContext context) {
    final c = SediHealthSubjectController.instance;
    return AnimatedBuilder(
      animation: c,
      builder: (context, _) {
        final active = c.activeSubject;
        final label = active == null
            ? l10n.activeSubjectUnknown
            : (active.isSelf
                ? l10n.activeSubjectSelf
                : '${l10n.activeSubjectFor} ${active.visibleName}');
        return Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 4),
          child: InkWell(
            onTap: c.accessibleSubjects.length <= 1
                ? null
                : () => _openPicker(context, c),
            borderRadius: BorderRadius.circular(8),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: AppTheme.gate2CardWhite.withOpacity(0.7),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  const Icon(Icons.person_outline, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      label,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                  ),
                  if (c.accessibleSubjects.length > 1)
                    const Icon(Icons.swap_horiz, size: 18),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  void _openPicker(BuildContext context, SediHealthSubjectController c) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppTheme.gate3PaleOliveBackground,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: ListView(
            shrinkWrap: true,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                child: Text(
                  l10n.selectSubject,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 16,
                  ),
                ),
              ),
              ...c.accessibleSubjects.map((s) {
                final selected = c.activeSubject?.id == s.id;
                final title = s.isSelf
                    ? '${l10n.activeSubjectSelf} (${s.visibleName})'
                    : s.visibleName;
                return ListTile(
                  title: Text(title),
                  trailing: selected
                      ? const Icon(Icons.check, color: AppTheme.pistachioGreen)
                      : null,
                  onTap: () {
                    c.selectSubject(s.id);
                    Navigator.of(ctx).pop();
                  },
                );
              }),
            ],
          ),
        );
      },
    );
  }
}
