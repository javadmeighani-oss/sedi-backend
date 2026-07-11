import 'dart:convert';
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/utils/user_profile_manager.dart';
import '../../../../core/utils/user_preferences.dart';
import '../../../../core/utils/messages.dart';
import '../../../../core/utils/gender_guess.dart';
import '../../../../data/models/user_profile.dart';
import '../../../../data/repositories/user_knowledge_repository.dart';
import '../../../../core/config/app_config.dart';
import '../../../../services/push/push_service.dart';
import '../../../chat/chat_service.dart';
import '../../../chat/presentation/pages/chat_page.dart';
import '../../../chat/presentation/widgets/sedi_header.dart';

/// LEGACY — not part of the 3-gate main route flow (Gate 1→2/3).
/// Superseded by `OtpLoginPage` + OTP auth. Kept for reference; do not wire into [AppGateRouter].
///
/// OnboardingPage – pre-OTP name/goals registration via `/interact/onboarding`.
const List<String> _goalKeys = [
  'better_sleep',
  'less_stress',
  'reduce_pain',
  'more_energy',
  'weight_management',
  'healthy_habits',
];

void _onboardingLog(String message) {
  if (kDebugMode) {
    debugPrint(message);
  }
}

class OnboardingPage extends StatefulWidget {
  const OnboardingPage({super.key});

  @override
  State<OnboardingPage> createState() => _OnboardingPageState();
}

class _OnboardingPageState extends State<OnboardingPage> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();

  bool _isFormValid = false;
  bool _isSubmitting = false;
  String _languagePref = 'auto';
  final List<String> _selectedGoals = [];

  String _getSystemLanguage() {
    final locale = ui.PlatformDispatcher.instance.locale;
    final languageCode = locale.languageCode.toLowerCase();
    if (languageCode == 'fa' || languageCode == 'ar') {
      return languageCode;
    }
    return 'fa';
  }

  @override
  void initState() {
    super.initState();
    _nameController.addListener(_validateForm);
    _checkOnboardingStatus();
    WidgetsBinding.instance.addPostFrameCallback((_) => _validateForm());
  }

  Future<void> _checkOnboardingStatus() async {
    try {
      final profile = await UserProfileManager.loadProfile();
      final hasName = profile.name != null && profile.name!.isNotEmpty;
      final isVerified = profile.isVerified;
      final hasCompletedOnboarding = hasName && isVerified;

      if (hasCompletedOnboarding && mounted) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (context) => const ChatPage()),
        );
      }
    } catch (e) {
      // Continue with onboarding page
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  void _validateForm() {
    final nameValid = _nameController.text.trim().isNotEmpty;
    if (mounted) {
      setState(() {
        _isFormValid = nameValid;
      });
    }
  }

  /// ============================================
  /// STEP 1: REWRITE ONBOARDING HANDLER (NO PATCHES)
  /// ============================================
  /// MANDATORY LOGIC:
  /// - Await HTTP response
  /// - Parse JSON
  /// - If (json["user_id"] != null):
  ///     - SAVE user_id
  ///     - MARK registration as SUCCESS
  ///     - NAVIGATE to chat screen
  ///     - RETURN IMMEDIATELY
  /// - ELSE:
  ///     - Show registration error
  /// ============================================
  Future<void> _submitForm() async {
_onboardingLog('[OnboardingPage] ========== SUBMIT FORM START ==========');

    // Pre-flight checks
    if (_isSubmitting || !_isFormValid) {
      _onboardingLog('[OnboardingPage] submit blocked');
      return;
    }

    if (!(_formKey.currentState?.validate() ?? false)) {
  _onboardingLog('[OnboardingPage] ⚠️ Form validation failed');
      return;
    }

    if (!mounted) {
  _onboardingLog('[OnboardingPage] ⚠️ Widget not mounted, aborting');
      return;
    }

    setState(() {
      _isSubmitting = true;
    });

    final name = _nameController.text.trim();
    final systemLanguage = _getSystemLanguage();

    Map<String, dynamic>? onboardingResponse;
    Exception? onboardingException;

    try {
  _onboardingLog('[OnboardingPage] ===== CALLING ONBOARDING API =====');
      final chatService = ChatService();
      // STEP 2: name is REQUIRED (non-empty, validated in form)
      onboardingResponse = await chatService.setupOnboarding(
        systemLanguage,
        name: name,
      );
  _onboardingLog('[OnboardingPage] ===== ONBOARDING API SUCCESS =====');
    } catch (e) {
      _onboardingLog('[OnboardingPage] onboarding API failed');
      onboardingException = e is Exception ? e : Exception(e.toString());
    }

    // ============================================
    // STEP 1: CHECK user_id (OUTSIDE try/catch)
    // ============================================
    // If HTTP request failed, show error
    if (onboardingException != null) {
  _onboardingLog('[OnboardingPage] ❌ HTTP request failed');
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
        final errorString = onboardingException.toString().toLowerCase();
        String errorMessage;
        if (errorString.contains('timeout') ||
            errorString.contains('connection') ||
            errorString.contains('network') ||
            errorString.contains('socket')) {
          errorMessage =
              'Connection error. Please check your internet and try again.';
        } else {
          errorMessage = 'Registration failed. Please try again.';
        }
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(errorMessage),
            backgroundColor: AppTheme.dangerRed,
            duration: const Duration(seconds: 5),
          ),
        );
      }
      return;
    }

    // Response received - parse it
    if (onboardingResponse == null) {
  _onboardingLog('[OnboardingPage] ❌ Response is null');
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Registration failed. Please try again.'),
            backgroundColor: AppTheme.dangerRed,
            duration: Duration(seconds: 5),
          ),
        );
      }
      return;
    }

    // Extract user_id
    final userId = onboardingResponse['user_id'];

    // Parse user_id to int
    int? userIdInt;
    if (userId == null) {
      userIdInt = null;
    } else if (userId is int) {
      userIdInt = userId;
    } else if (userId is String) {
      userIdInt = int.tryParse(userId);
    } else {
      userIdInt = int.tryParse(userId.toString());
    }

    // ============================================
    // STEP 1: CHECK user_id EXISTENCE
    // ============================================
    // If user_id is null → registration FAILED
    if (!AppConfig.useLocalMode && userIdInt == null) {
      _onboardingLog('[OnboardingPage] registration response missing user id');
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(onboardingResponse['message']?.toString() ??
                'Registration failed. Please try again.'),
            backgroundColor: AppTheme.dangerRed,
            duration: const Duration(seconds: 5),
          ),
        );
      }
      return;
    }

    // ============================================
    // STEP 1: SUCCESS PATH (user_id EXISTS)
    // ============================================
    // Registration is SUCCESSFUL
    // SAVE user_id, MARK as SUCCESS, NAVIGATE, RETURN IMMEDIATELY
    // ============================================
    _onboardingLog('[OnboardingPage] registration succeeded');
    _onboardingLog('[OnboardingPage] proceeding to save profile and navigate');

    // ============================================
    // STEP 2: HARD SEPARATION: onboarding vs chat
    // ============================================
    // After onboarding success:
    // - DO NOT auto-call chat API
    // - DO NOT wait for GPT
    // - DO NOT block navigation
    // - DO NOT show ANY error related to chat
    // Registration == user creation ONLY
    // ============================================

    // Soft gender guess from name (optional, not shown in UI)
    final guessed = guessGender(name, systemLanguage);
    final guessedGenderValue = guessedGenderToValue(guessed);

    try {
      final profile = UserProfile(
        name: name.isNotEmpty ? name : null,
        securityPassword: null,
        preferredLanguage:
            onboardingResponse['language']?.toString() ?? systemLanguage,
        userId: userIdInt,
        guessedGender: guessedGenderValue,
        hasSecurityPassword: false,
        securityPasswordSetAt: null,
        isVerified: true,
      );

      _onboardingLog('[OnboardingPage] saving profile');
      await UserProfileManager.saveProfile(profile);
      _onboardingLog('[OnboardingPage] profile saved');
      await tryRegisterStoredTokenAfterLogin();

      // Stage 24 UX Pack 02: persist get-to-know-you locally
      await UserPreferences.savePreferredName(name);
      await UserPreferences.saveLanguagePref(_languagePref);
      await UserPreferences.saveGoals(List<String>.from(_selectedGoals));
      await UserPreferences.setGetToKnowYouCompleted(true);

      // Best-effort backend sync (fail-open; do not block)
      if (userIdInt != null && !AppConfig.useLocalMode) {
        final resolvedLang =
            _languagePref == 'auto' ? systemLanguage : _languagePref;
        final goalsJson =
            _selectedGoals.isEmpty ? null : jsonEncode(_selectedGoals);
        try {
          final repo = UserKnowledgeRepository();
          final resp = await repo.upsertKnowledge(
            userId: userIdInt,
            displayName: name,
            language: resolvedLang,
            goalsJson: goalsJson,
          );
          if (!resp.ok) {
            _onboardingLog('[OnboardingPage] user knowledge sync failed');
          }
        } catch (_) {
          _onboardingLog('[OnboardingPage] user knowledge sync failed');
        }
      }
    } catch (saveError) {
      _onboardingLog('[OnboardingPage] profile save failed');
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Error saving profile. Please try again.'),
            backgroundColor: AppTheme.dangerRed,
            duration: Duration(seconds: 5),
          ),
        );
      }
      return;
    }

    // ============================================
    // STEP 3: KILL THE RED ERROR BANNER
    // ============================================
    // Navigation happens OUTSIDE try/catch
    // If navigation fails, it's a different error (not registration failure)
    // ============================================
    if (!mounted) {
  _onboardingLog('[OnboardingPage] ⚠️ Widget unmounted before navigation');
      return;
    }

    // Extract initial message (may be empty if chat failed - that's OK)
    final initialMessage = onboardingResponse['message']?.toString() ?? '';

    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (context) => ChatPage(initialMessage: initialMessage),
      ),
    );

    _onboardingLog('[OnboardingPage] navigation completed');
    _onboardingLog('[OnboardingPage] submit form finished');

    // Registration is COMPLETE - no error banner should appear
  }

  String _getGoalLabel(String key) {
    final lang = _getSystemLanguage();
    switch (key) {
      case 'better_sleep':
        return AppMessages.getGoalBetterSleep(lang);
      case 'less_stress':
        return AppMessages.getGoalLessStress(lang);
      case 'reduce_pain':
        return AppMessages.getGoalReducePain(lang);
      case 'more_energy':
        return AppMessages.getGoalMoreEnergy(lang);
      case 'weight_management':
        return AppMessages.getGoalWeightManagement(lang);
      case 'healthy_habits':
        return AppMessages.getGoalHealthyHabits(lang);
      default:
        return key;
    }
  }

  @override
  Widget build(BuildContext context) {
    final screenSize = MediaQuery.of(context).size;
    final containerWidth = screenSize.width * 0.9;
    final lang = _getSystemLanguage();

    return Scaffold(
      backgroundColor: AppTheme.backgroundWhite,
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 20, bottom: 16),
              child: SediHeader(
                isThinking: false,
                isAlert: false,
                size: 134.4,
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                child: Center(
                  child: Container(
                    width: containerWidth,
                    margin: const EdgeInsets.only(bottom: 24),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppTheme.metalGrey.withOpacity(0.3),
                      borderRadius:
                          BorderRadius.circular(AppTheme.radiusMedium),
                    ),
                    child: Form(
                      key: _formKey,
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          _buildNameSection(lang),
                          const SizedBox(height: 16),
                          _buildLanguageSection(lang),
                          const SizedBox(height: 16),
                          _buildGoalsSection(lang),
                          const SizedBox(height: 20),
                          _buildSubmitButton(),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNameSection(String lang) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 8, left: 4),
          child: Text(
            AppMessages.getPreferredNameLabel(lang),
            style: const TextStyle(
              color: AppTheme.textPrimary,
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
        Container(
          decoration: BoxDecoration(
            border: Border.all(color: AppTheme.primaryBlack, width: 1.5),
            borderRadius: BorderRadius.circular(AppTheme.radiusMedium),
          ),
          child: Container(
            decoration: BoxDecoration(
              color: AppTheme.metalGrey.withOpacity(0.2),
              borderRadius: BorderRadius.circular(AppTheme.radiusMedium - 1.5),
            ),
            child: TextFormField(
              controller: _nameController,
              decoration: InputDecoration(
                hintText: 'Enter your name',
                hintStyle:
                    TextStyle(color: AppTheme.textPrimary.withOpacity(0.5)),
                border: InputBorder.none,
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              ),
              style: const TextStyle(
                color: AppTheme.textPrimary,
                fontSize: 16,
              ),
              textDirection: TextDirection.ltr,
              validator: (value) {
                if (value == null || value.trim().isEmpty) {
                  return 'Please enter your name';
                }
                return null;
              },
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildLanguageSection(String lang) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 8, left: 4),
          child: Text(
            AppMessages.getLanguageLabel(lang),
            style: const TextStyle(
              color: AppTheme.textPrimary,
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
        Container(
          decoration: BoxDecoration(
            border: Border.all(color: AppTheme.primaryBlack, width: 1.5),
            borderRadius: BorderRadius.circular(AppTheme.radiusMedium),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: _languagePref,
              isExpanded: true,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              dropdownColor: AppTheme.metalGrey.withOpacity(0.95),
              items: const [
                DropdownMenuItem(value: 'auto', child: Text('Auto')),
                DropdownMenuItem(value: 'en', child: Text('English')),
                DropdownMenuItem(value: 'fa', child: Text('فارسی')),
                DropdownMenuItem(value: 'ar', child: Text('العربية')),
              ],
              onChanged: (value) {
                if (value != null) setState(() => _languagePref = value);
              },
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildGoalsSection(String lang) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 8, left: 4),
          child: Text(
            AppMessages.getGoalsLabel(lang),
            style: const TextStyle(
              color: AppTheme.textPrimary,
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: _goalKeys.map((key) {
            final selected = _selectedGoals.contains(key);
            final atMax = _selectedGoals.length >= 3 && !selected;
            return FilterChip(
              label: Text(_getGoalLabel(key)),
              selected: selected,
              onSelected: atMax
                  ? null
                  : (v) {
                      setState(() {
                        if (v) {
                          if (_selectedGoals.length < 3)
                            _selectedGoals.add(key);
                        } else {
                          _selectedGoals.remove(key);
                        }
                      });
                    },
              selectedColor: AppTheme.primaryBlack.withOpacity(0.2),
              checkmarkColor: AppTheme.primaryBlack,
            );
          }).toList(),
        ),
      ],
    );
  }

  Widget _buildSubmitButton() {
    const buttonSize = 58.0;
    const iconSize = 34.0;
    final isEnabled = _isFormValid && !_isSubmitting;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: isEnabled ? _submitForm : null,
      child: Container(
        width: buttonSize,
        height: buttonSize,
        decoration: BoxDecoration(
          color: isEnabled ? AppTheme.primaryBlack : AppTheme.metalGrey,
          shape: BoxShape.circle,
        ),
        child: _isSubmitting
            ? const Center(
                child: SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor:
                        AlwaysStoppedAnimation<Color>(AppTheme.backgroundWhite),
                  ),
                ),
              )
            : Icon(
                Icons.check,
                color: AppTheme.backgroundWhite,
                size: iconSize,
              ),
      ),
    );
  }
}
