import 'package:flutter/material.dart';

import '../../../../core/auth/auth_profile_service.dart';
import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/network/api_response.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../data/dto/auth/me_profile.dart';
import '../gate3_localization.dart';

/// Settings → Edit Profile — backend-confirmed /auth/me + I7 known-facts card.
class Gate3ProfilePage extends StatefulWidget {
  const Gate3ProfilePage({super.key});

  @override
  State<Gate3ProfilePage> createState() => _Gate3ProfilePageState();
}

class _Gate3ProfilePageState extends State<Gate3ProfilePage> {
  final _profile = AuthProfileService();
  final _api = ApiClient();
  MeProfileDto? _me;
  List<Map<String, String>> _facts = [];
  bool _loading = true;
  String? _error;

  Gate3Localization get _l10n =>
      Gate3Localization(SediLocaleController.instance.languageCode);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final meRes = await _profile.fetchMe(recoverSessionOn401: true);
    final factsRes = await _api.get<List<Map<String, String>>>(
      '/user/me/known-facts',
      parser: (data) {
        if (data is! Map) return <Map<String, String>>[];
        final raw = data['facts'];
        if (raw is! List) return <Map<String, String>>[];
        return raw
            .whereType<Map>()
            .map((e) => {
                  'category': e['category']?.toString() ?? '',
                  'text': e['text']?.toString() ?? '',
                })
            .where((e) => e['text']!.isNotEmpty)
            .toList();
      },
    );

    if (!mounted) return;
    setState(() {
      _loading = false;
      if (!meRes.ok || meRes.data == null) {
        _error = meRes.errorMessage;
      } else {
        _me = meRes.data;
        final lang = meRes.data!.preferredLanguage;
        if (lang != null && lang.isNotEmpty) {
          SediLocaleController.instance.reconcileFromBackendConfirmed(lang);
        }
      }
      if (factsRes.ok && factsRes.data != null) {
        _facts = factsRes.data!;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    return Scaffold(
      backgroundColor: AppTheme.gate3PaleOliveBackground,
      appBar: AppBar(
        title: Text(l10n.editProfile),
        backgroundColor: AppTheme.gate3PaleOliveBackground,
        foregroundColor: AppTheme.textPrimary,
        elevation: 0,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
                children: [
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(_error!, style: const TextStyle(color: AppTheme.dangerRed)),
                    ),
                  _sectionTitle(l10n.editProfile),
                  _field(l10n.profileNameLabel, _me?.name ?? '—'),
                  _field(l10n.profileDobLabel, _formatDob(_me)),
                  _field(l10n.profileSexLabel, _me?.sex ?? '—'),
                  _field(l10n.profilePhoneLabel, _me?.phone ?? '—'),
                  const SizedBox(height: 8),
                  Text(
                    l10n.phoneChangeDeferred,
                    style: const TextStyle(
                      color: AppTheme.textSecondary,
                      fontSize: 13,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 24),
                  _sectionTitle(l10n.whatSediKnows),
                  if (_facts.isEmpty)
                    Text(
                      l10n.whatSediKnowsEmpty,
                      style: const TextStyle(color: AppTheme.textSecondary),
                    )
                  else
                    ..._facts.map(
                      (f) => Card(
                        color: AppTheme.gate2CardWhite,
                        elevation: 0,
                        margin: const EdgeInsets.only(bottom: 8),
                        child: ListTile(
                          title: Text(f['category'] ?? ''),
                          subtitle: Text(f['text'] ?? ''),
                        ),
                      ),
                    ),
                ],
              ),
            ),
    );
  }

  String _formatDob(MeProfileDto? me) {
    if (me == null) return '—';
    if (me.dateOfBirth != null && me.dateOfBirth!.isNotEmpty) {
      return me.dateOfBirth!;
    }
    if (me.birthYear != null) {
      return '${me.birthYear}-${me.birthMonth ?? '?'}-${me.birthDay ?? '?'}';
    }
    return '—';
  }

  Widget _sectionTitle(String t) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Text(
          t,
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: AppTheme.textPrimary,
          ),
        ),
      );

  Widget _field(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
            const SizedBox(height: 2),
            Text(value, style: const TextStyle(fontSize: 16, color: AppTheme.textPrimary)),
          ],
        ),
      );
}
