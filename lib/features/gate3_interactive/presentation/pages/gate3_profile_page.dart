import 'package:flutter/material.dart';

import '../../../../core/auth/auth_helper.dart';
import '../../../../core/auth/auth_otp_service.dart';
import '../../../../core/auth/auth_profile_service.dart';
import '../../../../core/locale/sedi_locale_controller.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../data/dto/auth/me_profile.dart';
import '../../../auth_otp/presentation/a2_phone_e164.dart';
import '../gate3_localization.dart';

/// A3 Profile — exactly 3 sections: User info, I6/I8 summary, Log out.
class Gate3ProfilePage extends StatefulWidget {
  const Gate3ProfilePage({super.key});

  @override
  State<Gate3ProfilePage> createState() => _Gate3ProfilePageState();
}

class _Gate3ProfilePageState extends State<Gate3ProfilePage> {
  final _profile = AuthProfileService();
  final _otp = AuthOtpService();
  final _api = ApiClient();
  final _phoneCtrl = TextEditingController();
  final _otpCtrl = TextEditingController();

  MeProfileDto? _me;
  List<Map<String, String>> _summaryRows = [];
  bool _loading = true;
  String? _error;
  String? _phoneFlowError;
  String? _phoneFlowSuccess;
  bool _changingPhone = false;
  bool _otpSent = false;
  bool _phoneBusy = false;
  String? _pendingNewPhone;
  A2CountryDialCode _dial = A2PhoneE164.defaultDialCode;

  Gate3Localization get _l10n =>
      Gate3Localization(SediLocaleController.instance.languageCode);

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _phoneCtrl.dispose();
    _otpCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final meRes = await _profile.fetchMe(recoverSessionOn401: true);
    final summaryRes = await _api.get<List<Map<String, String>>>(
      '/auth/me/profile-summary',
      parser: (data) {
        if (data is! Map) return <Map<String, String>>[];
        final raw = data['rows'];
        if (raw is! List) return <Map<String, String>>[];
        return raw
            .whereType<Map>()
            .map(
              (e) => {
                'key': e['key']?.toString() ?? '',
                'status': e['status']?.toString() ?? '',
              },
            )
            .where((e) => e['key']!.isNotEmpty && e['status']!.isNotEmpty)
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
      if (summaryRes.ok && summaryRes.data != null) {
        _summaryRows = summaryRes.data!;
      } else {
        _summaryRows = [];
      }
    });
  }

  String _mapPhoneError(String? code, String? message) {
    final l10n = _l10n;
    switch ((code ?? '').toUpperCase()) {
      case 'PHONE_INVALID':
        return l10n.phoneInvalid;
      case 'PHONE_SAME':
        return l10n.phoneSame;
      case 'PHONE_DUPLICATE':
        return l10n.phoneDuplicate;
      case 'OTP_INVALID':
        return l10n.phoneOtpInvalid;
      case 'OTP_EXPIRED':
        return l10n.phoneOtpExpired;
      case 'OTP_RATE_LIMITED':
      case 'TOO_MANY_ATTEMPTS':
        return l10n.phoneOtpRateLimited;
      default:
        if (message != null && message.trim().isNotEmpty) return message;
        return l10n.phoneChangeNetworkError;
    }
  }

  Future<void> _requestPhoneOtp() async {
    final l10n = _l10n;
    final e164 = A2PhoneE164.normalize(
      nationalInput: _phoneCtrl.text,
      dialCode: _dial,
    );
    if (!A2PhoneE164.isValid(
      nationalInput: _phoneCtrl.text,
      dialCode: _dial,
    )) {
      setState(() => _phoneFlowError = l10n.phoneInvalid);
      return;
    }
    final current = (_me?.phone ?? '').trim();
    if (current.isNotEmpty && current == e164) {
      setState(() => _phoneFlowError = l10n.phoneSame);
      return;
    }

    setState(() {
      _phoneBusy = true;
      _phoneFlowError = null;
      _phoneFlowSuccess = null;
    });
    final lang = SediLocaleController.instance.languageCode;
    final res = await _otp.requestPhoneChangeOtp(newPhone: e164, language: lang);
    if (!mounted) return;
    setState(() {
      _phoneBusy = false;
      if (!res.ok) {
        _phoneFlowError = _mapPhoneError(res.error?.code, res.errorMessage);
        _otpSent = false;
        _pendingNewPhone = null;
      } else {
        _otpSent = true;
        _pendingNewPhone = e164;
        _otpCtrl.clear();
      }
    });
  }

  Future<void> _verifyPhoneOtp() async {
    final pending = _pendingNewPhone;
    if (pending == null || pending.isEmpty) return;
    final code = _otpCtrl.text.trim();
    setState(() {
      _phoneBusy = true;
      _phoneFlowError = null;
      _phoneFlowSuccess = null;
    });
    final res = await _otp.verifyPhoneChangeOtp(newPhone: pending, code: code);
    if (!mounted) return;
    if (!res.ok || res.data == null) {
      setState(() {
        _phoneBusy = false;
        _phoneFlowError = _mapPhoneError(res.error?.code, res.errorMessage);
      });
      return;
    }
    final meRes = await _profile.fetchMe(recoverSessionOn401: true);
    if (!mounted) return;
    setState(() {
      _phoneBusy = false;
      if (meRes.ok && meRes.data != null) {
        _me = meRes.data;
      } else {
        _me = res.data;
      }
      _changingPhone = false;
      _otpSent = false;
      _pendingNewPhone = null;
      _phoneCtrl.clear();
      _otpCtrl.clear();
      _phoneFlowSuccess = _l10n.phoneChangeSuccess;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    final textDir =
        l10n.isRtl ? TextDirection.rtl : TextDirection.ltr;
    return Directionality(
      textDirection: textDir,
      child: Scaffold(
        backgroundColor: AppTheme.gate3PaleOliveBackground,
        appBar: AppBar(
          title: Text(l10n.profileTitle),
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
                        child: Text(
                          _error!,
                          style: const TextStyle(color: AppTheme.dangerRed),
                        ),
                      ),
                    // --- Section 1: User information ---
                    _sectionTitle(l10n.userInformationSection),
                    _field(l10n.profileNameLabel, _me?.name ?? '—'),
                    _field(l10n.profileDobLabel, _formatDob(_me)),
                    _field(l10n.profileSexLabel, _me?.sex ?? '—'),
                    _field(
                      l10n.profileLanguageLabel,
                      _me?.preferredLanguage ?? '—',
                    ),
                    _field(l10n.profilePhoneLabel, _me?.phone ?? '—'),
                    const SizedBox(height: 8),
                    if (!_changingPhone)
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton(
                          onPressed: () => setState(() {
                            _changingPhone = true;
                            _phoneFlowError = null;
                            _phoneFlowSuccess = null;
                            _otpSent = false;
                          }),
                          child: Text(l10n.changePhone),
                        ),
                      ),
                    if (_changingPhone) ..._phoneChangeWidgets(l10n),
                    if (!_changingPhone && _phoneFlowSuccess != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Text(
                          _phoneFlowSuccess!,
                          style: const TextStyle(color: AppTheme.textPrimary),
                        ),
                      ),
                    const SizedBox(height: 28),
                    // --- Section 2: User summary ---
                    _sectionTitle(l10n.userSummarySection),
                    if (_summaryRows.isEmpty)
                      Text(
                        l10n.userSummaryEmpty,
                        style: const TextStyle(color: AppTheme.textSecondary),
                      )
                    else
                      ..._summaryRows.map(
                        (row) => _summaryRow(
                          l10n.summaryRowLabel(row['key']!),
                          l10n.summaryStatusLabel(row['status']!),
                        ),
                      ),
                    const SizedBox(height: 36),
                    // --- Section 3: Log out ---
                    _sectionTitle(l10n.logoutSection),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: () =>
                            AuthHelper.performLogout(context: context),
                        icon: const Icon(Icons.logout_rounded),
                        label: Text(l10n.logout),
                      ),
                    ),
                  ],
                ),
              ),
      ),
    );
  }

  List<Widget> _phoneChangeWidgets(Gate3Localization l10n) {
    return [
      const SizedBox(height: 8),
      Text(
        l10n.newPhoneLabel,
        style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12),
      ),
      const SizedBox(height: 6),
      Row(
        children: [
          DropdownButton<A2CountryDialCode>(
            value: _dial,
            items: A2PhoneE164.dialCodes
                .map(
                  (c) => DropdownMenuItem(
                    value: c,
                    child: Text(c.displayDial),
                  ),
                )
                .toList(),
            onChanged: _phoneBusy
                ? null
                : (v) {
                    if (v != null) setState(() => _dial = v);
                  },
          ),
          const SizedBox(width: 8),
          Expanded(
            child: TextField(
              controller: _phoneCtrl,
              enabled: !_phoneBusy && !_otpSent,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                isDense: true,
                border: OutlineInputBorder(),
              ),
            ),
          ),
        ],
      ),
      if (_otpSent) ...[
        const SizedBox(height: 12),
        Text(
          l10n.otpCodeLabel,
          style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12),
        ),
        const SizedBox(height: 6),
        TextField(
          controller: _otpCtrl,
          enabled: !_phoneBusy,
          keyboardType: TextInputType.number,
          maxLength: 6,
          decoration: const InputDecoration(
            isDense: true,
            border: OutlineInputBorder(),
            counterText: '',
          ),
        ),
      ],
      if (_phoneFlowError != null)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(
            _phoneFlowError!,
            style: const TextStyle(color: AppTheme.dangerRed),
          ),
        ),
      if (_phoneFlowSuccess != null)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(
            _phoneFlowSuccess!,
            style: const TextStyle(color: AppTheme.textPrimary),
          ),
        ),
      const SizedBox(height: 12),
      Row(
        children: [
          if (!_otpSent)
            ElevatedButton(
              onPressed: _phoneBusy ? null : _requestPhoneOtp,
              child: _phoneBusy
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(l10n.sendPhoneOtp),
            )
          else
            ElevatedButton(
              onPressed: _phoneBusy ? null : _verifyPhoneOtp,
              child: _phoneBusy
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(l10n.verifyPhoneOtp),
            ),
          const SizedBox(width: 12),
          TextButton(
            onPressed: _phoneBusy
                ? null
                : () => setState(() {
                      _changingPhone = false;
                      _otpSent = false;
                      _pendingNewPhone = null;
                      _phoneFlowError = null;
                    }),
            child: Text(l10n.cancel),
          ),
        ],
      ),
    ];
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
            Text(
              label,
              style: const TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 12,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              value,
              style: const TextStyle(
                fontSize: 16,
                color: AppTheme.textPrimary,
              ),
            ),
          ],
        ),
      );

  Widget _summaryRow(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              flex: 5,
              child: Text(
                label,
                style: const TextStyle(
                  color: AppTheme.textSecondary,
                  fontSize: 13,
                ),
              ),
            ),
            Expanded(
              flex: 4,
              child: Text(
                value,
                textAlign: TextAlign.end,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: AppTheme.textPrimary,
                ),
              ),
            ),
          ],
        ),
      );
}
