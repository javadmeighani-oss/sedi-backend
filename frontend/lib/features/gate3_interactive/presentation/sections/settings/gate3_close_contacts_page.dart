import 'package:flutter/material.dart';

import '../../../../../core/theme/app_theme.dart';
import '../../../../../core/widgets/app_states/app_empty_state.dart';
import '../../../../../core/widgets/app_states/app_error_state.dart';
import '../../../../../core/widgets/app_states/app_loading_state.dart';
import '../../../../../data/dto/gate3/caregiver_dto.dart';
import '../../../logic/close_contacts_controller.dart';
import '../../../logic/gate3_phone_utils.dart';
import '../../gate3_sections_localization.dart';
import '../../widgets/gate3_section_card.dart';
import '../../widgets/gate3_section_scaffold.dart';

class Gate3CloseContactsPage extends StatefulWidget {
  final String lang;

  const Gate3CloseContactsPage({super.key, required this.lang});

  @override
  State<Gate3CloseContactsPage> createState() => _Gate3CloseContactsPageState();
}

class _Gate3CloseContactsPageState extends State<Gate3CloseContactsPage> {
  late final CloseContactsController _controller;

  @override
  void initState() {
    super.initState();
    _controller = CloseContactsController(lang: widget.lang);
    _controller.addListener(_onChanged);
    _controller.load();
  }

  @override
  void dispose() {
    _controller.removeListener(_onChanged);
    _controller.dispose();
    super.dispose();
  }

  void _onChanged() {
    if (mounted) setState(() {});
  }

  Gate3SectionsLocalization get l10n => Gate3SectionsLocalization(widget.lang);

  @override
  Widget build(BuildContext context) {
    return Gate3SectionScaffold(
      lang: widget.lang,
      title: l10n.closeContactsTitle,
      isRefreshing: _controller.refreshing,
      onRefresh: () => _controller.load(isRefresh: true),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_controller.loading && _controller.contacts.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [AppLoadingState(label: l10n.loading)],
      );
    }

    if (_controller.error != null && _controller.contacts.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          AppErrorState(
            message: _controller.error!,
            onRetry: () => _controller.load(),
          ),
        ],
      );
    }

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        if (_controller.actionMessage != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              _controller.actionMessage!,
              style: const TextStyle(color: AppTheme.gate2ButtonOlive),
            ),
          ),
        if (_controller.contacts.isEmpty)
          AppEmptyState(
            title: l10n.noContactsTitle,
            subtitle: l10n.noContactsSubtitle,
          )
        else
          ..._controller.contacts.map(_contactCard),
        const SizedBox(height: 12),
        FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: AppTheme.gate2ButtonOlive,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
            ),
          ),
          onPressed: () => _openForm(),
          icon: const Icon(Icons.add_rounded),
          label: Text(l10n.addContact),
        ),
      ],
    );
  }

  Widget _contactCard(CaregiverDto c) {
    final phoneValid = c.phone != null && Gate3PhoneUtils.isValid(c.phone!);
    return Gate3SectionCard(
      title: c.name,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (c.phone != null && c.phone!.isNotEmpty)
            Text(c.phone!, style: const TextStyle(color: AppTheme.textSecondary)),
          if (c.relationship != null && c.relationship!.isNotEmpty)
            Text(c.relationship!, style: const TextStyle(color: AppTheme.textSecondary)),
          const SizedBox(height: 10),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(l10n.prefDailyReport),
            value: c.notifyDailyStatus,
            activeColor: AppTheme.gate2ButtonOlive,
            onChanged: (v) => _savePrefs(c, notifyDaily: v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(l10n.prefCareSummary),
            value: c.notifyCareSummary,
            activeColor: AppTheme.gate2ButtonOlive,
            onChanged: _controller.isSaving(c.id)
                ? null
                : (v) => _savePrefs(c, notifyCareSummary: v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(l10n.prefVitalAlerts),
            subtitle: Text(
              l10n.prefVitalAlertsUnavailable,
              style: const TextStyle(fontSize: 12),
            ),
            value: c.notifyVitalAlerts,
            activeColor: AppTheme.gate2ButtonOlive,
            onChanged: _controller.isSaving(c.id)
                ? null
                : (v) => _savePrefs(c, notifyVitalAlerts: v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(l10n.prefEmergencyBySedi),
            subtitle: Text(l10n.emergencyExplanation,
                style: const TextStyle(fontSize: 12)),
            value: c.notifyEmergency,
            activeColor: AppTheme.gate2ButtonOlive,
            onChanged: (v) => _savePrefs(c, notifyEmergency: v),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              TextButton.icon(
                onPressed: () => _openForm(existing: c),
                icon: const Icon(Icons.edit_outlined, size: 18),
                label: Text(l10n.editContact),
              ),
              const Spacer(),
              IconButton(
                tooltip: l10n.manualCall,
                onPressed: null,
                icon: Icon(
                  Icons.phone_outlined,
                  color: phoneValid
                      ? AppTheme.textSecondary.withOpacity(0.4)
                      : AppTheme.textSecondary.withOpacity(0.25),
                ),
              ),
            ],
          ),
          Text(
            l10n.manualCallUnavailable,
            style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary),
          ),
        ],
      ),
    );
  }

  Future<void> _savePrefs(
    CaregiverDto c, {
    bool? notifyDaily,
    bool? notifyEmergency,
    bool? notifyCareSummary,
    bool? notifyVitalAlerts,
  }) async {
    await _controller.saveContact(
      existing: c,
      name: c.name,
      phone: c.phone,
      relationship: c.relationship,
      notifyDailyStatus: notifyDaily ?? c.notifyDailyStatus,
      notifyEmergency: notifyEmergency ?? c.notifyEmergency,
      notifyCareSummary: notifyCareSummary ?? c.notifyCareSummary,
      notifyVitalAlerts: notifyVitalAlerts ?? c.notifyVitalAlerts,
      emergencyPriority: c.emergencyPriority,
    );
  }

  Future<void> _openForm({CaregiverDto? existing}) async {
    final nameCtrl = TextEditingController(text: existing?.name ?? '');
    final phoneCtrl = TextEditingController(text: existing?.phone ?? '');
    final relCtrl = TextEditingController(text: existing?.relationship ?? '');

    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.gate3PaleOliveBackground,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return Padding(
          padding: EdgeInsets.only(
            left: 20,
            right: 20,
            top: 16,
            bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                existing == null ? l10n.addContact : l10n.editContact,
                style: const TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: nameCtrl,
                decoration: InputDecoration(labelText: l10n.nameLabel),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: phoneCtrl,
                keyboardType: TextInputType.phone,
                decoration: InputDecoration(labelText: l10n.phoneLabel),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: relCtrl,
                decoration: InputDecoration(labelText: l10n.relationshipLabel),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  if (existing != null)
                    TextButton(
                      onPressed: () async {
                        final ok = await showDialog<bool>(
                          context: ctx,
                          builder: (dCtx) => AlertDialog(
                            title: Text(l10n.deleteContact),
                            content: Text(l10n.deleteContactConfirm),
                            actions: [
                              TextButton(
                                onPressed: () => Navigator.pop(dCtx, false),
                                child: Text(l10n.cancel),
                              ),
                              TextButton(
                                onPressed: () => Navigator.pop(dCtx, true),
                                child: Text(l10n.deleteContact),
                              ),
                            ],
                          ),
                        );
                        if (ok == true) {
                          await _controller.removeContact(existing);
                          if (ctx.mounted) Navigator.pop(ctx, true);
                        }
                      },
                      child: Text(
                        l10n.deleteContact,
                        style: const TextStyle(color: AppTheme.dangerRed),
                      ),
                    ),
                  const Spacer(),
                  TextButton(
                    onPressed: () => Navigator.pop(ctx, false),
                    child: Text(l10n.cancel),
                  ),
                  FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: AppTheme.gate2ButtonOlive,
                    ),
                    onPressed: () async {
                      if (nameCtrl.text.trim().isEmpty) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(l10n.nameRequired)),
                        );
                        return;
                      }
                      final phone = phoneCtrl.text.trim();
                      if (phone.isNotEmpty && !Gate3PhoneUtils.isValid(phone)) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(l10n.invalidPhone)),
                        );
                        return;
                      }
                      final ok = await _controller.saveContact(
                        existing: existing,
                        name: nameCtrl.text.trim(),
                        phone: phone.isEmpty
                            ? null
                            : Gate3PhoneUtils.normalize(phone),
                        relationship: relCtrl.text.trim().isEmpty
                            ? null
                            : relCtrl.text.trim(),
                        notifyDailyStatus: existing?.notifyDailyStatus ?? false,
                        notifyEmergency: existing?.notifyEmergency ?? true,
                        notifyCareSummary:
                            existing?.notifyCareSummary ?? false,
                      );
                      if (ctx.mounted) Navigator.pop(ctx, ok);
                    },
                    child: Text(l10n.save),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );

    if (saved == true && mounted) setState(() {});
  }
}
