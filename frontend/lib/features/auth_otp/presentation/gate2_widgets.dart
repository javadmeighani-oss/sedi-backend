import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_theme.dart';
import 'birth_calendar_helper.dart';
import 'otp_login_localization.dart';

/// Shared luxury UI primitives for Gate 2 internal steps.
class Gate2Widgets {
  Gate2Widgets._();

  static Widget pageShell({
    required Widget child,
    required bool isLoading,
    required String loadingLabel,
  }) {
    return Stack(
      children: [
        child,
        if (isLoading)
          Container(
            color: AppTheme.gate2WarmBackground.withOpacity(0.5),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(
                    color: AppTheme.gate2ButtonOlive,
                    strokeWidth: 2,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    loadingLabel,
                    style: AppTheme.bodySecondary.copyWith(
                      color: AppTheme.gate2TextPrimary,
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  static Widget centeredLuxuryCard({required Widget child}) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Container(
          width: double.infinity,
          decoration: BoxDecoration(
            color: AppTheme.gate2CardWhite,
            borderRadius: BorderRadius.circular(AppTheme.gate2RadiusCard),
            boxShadow: AppTheme.gate2CardShadow,
            border: Border.all(
              color: AppTheme.gate2BorderSubtle,
              width: 0.5,
            ),
          ),
          padding: const EdgeInsets.fromLTRB(24, 28, 24, 28),
          child: child,
        ),
      ),
    );
  }

  static Widget stepTitle(String title, {String? subtitle}) {
    return Column(
      children: [
        Text(
          title,
          textAlign: TextAlign.center,
          style: const TextStyle(
            color: AppTheme.gate2TextPrimary,
            fontSize: 22,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.2,
          ),
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 10),
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppTheme.gate2TextMuted,
              fontSize: 14,
              height: 1.5,
            ),
          ),
        ],
      ],
    );
  }

  static Widget languageButton({
    required String label,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: Material(
        color: selected
            ? AppTheme.gate2ButtonActive
            : AppTheme.gate2InputFill,
        borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 14),
            alignment: Alignment.center,
            child: Text(
              label,
              style: TextStyle(
                color: selected
                    ? AppTheme.gate2CardWhite
                    : AppTheme.gate2TextPrimary,
                fontSize: 16,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
          ),
        ),
      ),
    );
  }

  static Widget accountOptionCard({
    required String title,
    required String description,
    required IconData icon,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: AppTheme.gate2InputFill,
        borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
        border: Border.all(
          color: selected
              ? AppTheme.gate2ButtonOlive
              : AppTheme.gate2BorderSubtle,
          width: selected ? 1.5 : 0.8,
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  icon,
                  color: selected
                      ? AppTheme.gate2ButtonOlive
                      : AppTheme.gate2TextMuted,
                  size: 22,
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          color: AppTheme.gate2TextPrimary,
                          fontSize: 16,
                          fontWeight:
                              selected ? FontWeight.w600 : FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        description,
                        style: const TextStyle(
                          color: AppTheme.gate2TextMuted,
                          fontSize: 13,
                          height: 1.45,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  static Widget backLink({
    required String label,
    required VoidCallback onPressed,
  }) {
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: TextButton.icon(
        onPressed: onPressed,
        icon: const Icon(
          Icons.arrow_back_ios_new_rounded,
          size: 16,
          color: AppTheme.gate2TextMuted,
        ),
        label: Text(
          label,
          style: const TextStyle(
            color: AppTheme.gate2TextMuted,
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }

  static Widget secondaryButton({
    required String label,
    required bool enabled,
    required VoidCallback onPressed,
    bool fullWidth = true,
  }) {
    return SizedBox(
      width: fullWidth ? double.infinity : null,
      height: 50,
      child: OutlinedButton(
        onPressed: enabled ? onPressed : null,
        style: OutlinedButton.styleFrom(
          foregroundColor: AppTheme.gate2TextPrimary,
          disabledForegroundColor: AppTheme.gate2TextDisabled,
          side: BorderSide(
            color: enabled
                ? AppTheme.gate2BorderSubtle
                : AppTheme.gate2ButtonDisabled,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
          ),
        ),
        child: Text(
          label,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
      ),
    );
  }

  static Widget correctionPanel({
    required String message,
    required String primaryLabel,
    required VoidCallback onPrimary,
    required String secondaryLabel,
    required VoidCallback onSecondary,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.gate2InputFill,
            borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
            border: Border.all(color: AppTheme.gate2BorderSubtle, width: 0.8),
          ),
          child: Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppTheme.gate2TextPrimary,
              fontSize: 15,
              height: 1.55,
            ),
          ),
        ),
        const SizedBox(height: 20),
        primaryButton(
          label: primaryLabel,
          enabled: true,
          onPressed: onPrimary,
        ),
        const SizedBox(height: 10),
        secondaryButton(
          label: secondaryLabel,
          enabled: true,
          onPressed: onSecondary,
        ),
      ],
    );
  }

  static Widget textLinkButton({
    required String label,
    required VoidCallback onPressed,
  }) {
    return Center(
      child: TextButton(
        onPressed: onPressed,
        child: Text(
          label,
          style: const TextStyle(
            color: AppTheme.gate2TextMuted,
            fontSize: 14,
            fontWeight: FontWeight.w500,
            decoration: TextDecoration.underline,
            decorationColor: AppTheme.gate2TextMuted,
          ),
        ),
      ),
    );
  }

  static Widget primaryButton({
    required String label,
    required bool enabled,
    required VoidCallback onPressed,
    bool fullWidth = true,
  }) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      width: fullWidth ? double.infinity : null,
      height: 50,
      child: ElevatedButton(
        onPressed: enabled ? onPressed : null,
        style: ElevatedButton.styleFrom(
          backgroundColor:
              enabled ? AppTheme.gate2ButtonOlive : AppTheme.gate2ButtonDisabled,
          disabledBackgroundColor: AppTheme.gate2ButtonDisabled,
          foregroundColor: AppTheme.gate2CardWhite,
          disabledForegroundColor: AppTheme.gate2TextDisabled,
          elevation: enabled ? 1 : 0,
          shadowColor: Colors.black26,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
          ),
        ),
        child: Text(
          label,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
      ),
    );
  }

  static Widget textField({
    required TextEditingController controller,
    required String hint,
    required IconData icon,
    String? Function(String?)? validator,
    TextInputType keyboardType = TextInputType.text,
    List<TextInputFormatter>? inputFormatters,
    ValueChanged<String>? onChanged,
    bool readOnly = false,
  }) {
    return TextFormField(
      controller: controller,
      validator: validator,
      keyboardType: keyboardType,
      inputFormatters: inputFormatters,
      onChanged: onChanged,
      readOnly: readOnly,
      enableInteractiveSelection: !readOnly,
      style: const TextStyle(
        color: AppTheme.gate2TextPrimary,
        fontSize: 16,
      ),
      decoration: _inputDecoration(hint, icon),
    );
  }

  static InputDecoration _inputDecoration(String hint, IconData icon) {
    return InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(
        color: AppTheme.gate2Placeholder,
        fontWeight: FontWeight.w400,
      ),
      filled: true,
      fillColor: AppTheme.gate2InputFill,
      prefixIcon: Icon(icon, color: AppTheme.gate2TextMuted, size: 20),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 15),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
        borderSide: const BorderSide(color: AppTheme.gate2BorderSubtle, width: 0.8),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
        borderSide: const BorderSide(color: AppTheme.gate2ButtonActive, width: 1.2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
        borderSide: const BorderSide(color: AppTheme.gate2ButtonActive, width: 0.8),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
        borderSide: const BorderSide(color: AppTheme.gate2ButtonActive, width: 1.2),
      ),
    );
  }

  static Widget tapField({
    required String hint,
    required String value,
    required IconData icon,
    required VoidCallback onTap,
    bool hasError = false,
    String? errorText,
  }) {
    final hasValue = value.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
          child: InputDecorator(
            decoration: _inputDecoration(hint, icon).copyWith(
              errorBorder: hasError
                  ? OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(AppTheme.gate2RadiusInput),
                      borderSide: const BorderSide(
                        color: AppTheme.gate2ButtonActive,
                        width: 0.8,
                      ),
                    )
                  : null,
            ),
            child: Text(
              hasValue ? value : hint,
              style: TextStyle(
                color: hasValue
                    ? AppTheme.gate2TextPrimary
                    : AppTheme.gate2Placeholder,
                fontSize: 16,
              ),
            ),
          ),
        ),
        if (hasError && errorText != null)
          Padding(
            padding: const EdgeInsets.only(top: 6, left: 12, right: 12),
            child: Text(
              errorText,
              style: const TextStyle(color: AppTheme.dangerRed, fontSize: 12),
            ),
          ),
      ],
    );
  }

  static Widget dobPicker({
    required OtpLoginLocalization l10n,
    required String calendarType,
    required int day,
    required int month,
    required int year,
    required ValueChanged<int> onDay,
    required ValueChanged<int> onMonth,
    required ValueChanged<int> onYear,
  }) {
    final days = List<int>.generate(
      BirthCalendarHelper.daysInMonth(
        calendarType: calendarType,
        year: year,
        month: month,
      ),
      (i) => i + 1,
    );
    final months = List<int>.generate(12, (i) => i + 1);
    final years = BirthCalendarHelper.yearRange(calendarType);
    final safeDay = day.clamp(1, days.last);

    return Container(
      margin: const EdgeInsets.only(top: 8),
      decoration: BoxDecoration(
        color: AppTheme.gate2InputFill,
        borderRadius: BorderRadius.circular(AppTheme.gate2RadiusInput),
        border: Border.all(color: AppTheme.gate2BorderSubtle, width: 0.8),
      ),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    l10n.day,
                    textAlign: TextAlign.center,
                    style: _pickerHeaderStyle,
                  ),
                ),
                _pickerDivider(),
                Expanded(
                  flex: 2,
                  child: Text(
                    l10n.month,
                    textAlign: TextAlign.center,
                    style: _pickerHeaderStyle,
                  ),
                ),
                _pickerDivider(),
                Expanded(
                  child: Text(
                    l10n.year,
                    textAlign: TextAlign.center,
                    style: _pickerHeaderStyle,
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1, thickness: 0.8, color: AppTheme.gate2BorderSubtle),
          SizedBox(
            height: 132,
            child: Row(
              children: [
                Expanded(
                  child: _wheelColumn(
                    items: days,
                    selected: safeDay,
                    label: (v) => l10n.formatDay(v),
                    onSelected: onDay,
                  ),
                ),
                _pickerDivider(height: 132),
                Expanded(
                  flex: 2,
                  child: _wheelColumn(
                    items: months,
                    selected: month,
                    label: (v) => l10n.months[v - 1],
                    onSelected: onMonth,
                  ),
                ),
                _pickerDivider(height: 132),
                Expanded(
                  child: _wheelColumn(
                    items: years,
                    selected: year,
                    label: (v) => l10n.formatYear(v),
                    onSelected: onYear,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static const _pickerHeaderStyle = TextStyle(
    color: AppTheme.gate2TextPrimary,
    fontSize: 12,
    fontWeight: FontWeight.w600,
  );

  static Widget _pickerDivider({double height = 18}) {
    return Container(
      width: 0.8,
      height: height,
      color: AppTheme.gate2BorderSubtle,
    );
  }

  static Widget _wheelColumn({
    required List<int> items,
    required int selected,
    required String Function(int) label,
    required ValueChanged<int> onSelected,
  }) {
    return ListWheelScrollView.useDelegate(
      itemExtent: 34,
      diameterRatio: 1.5,
      physics: const FixedExtentScrollPhysics(),
      controller: FixedExtentScrollController(
        initialItem: items.indexOf(selected).clamp(0, items.length - 1),
      ),
      onSelectedItemChanged: (index) => onSelected(items[index]),
      childDelegate: ListWheelChildBuilderDelegate(
        childCount: items.length,
        builder: (context, index) {
          final value = items[index];
          final isSelected = value == selected;
          return Center(
            child: Text(
              label(value),
              style: TextStyle(
                color: AppTheme.gate2TextPrimary,
                fontSize: isSelected ? 15 : 13,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
          );
        },
      ),
    );
  }

  static Widget otpSection({
    required OtpLoginLocalization l10n,
    required List<TextEditingController> controllers,
    required List<FocusNode> focusNodes,
    required TextEditingController autofillController,
    required bool active,
    String? helperText,
    bool showTitle = true,
  }) {
    final title = active ? l10n.sentCode : (helperText ?? l10n.otpEnterAfterSend);
    return Column(
      children: [
        if (showTitle) ...[
          Text(
            title,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: active
                  ? AppTheme.gate2TextPrimary
                  : AppTheme.gate2TextMuted,
              fontSize: active ? 16 : 14,
              fontWeight: active ? FontWeight.w600 : FontWeight.w400,
              height: 1.45,
            ),
          ),
          const SizedBox(height: 18),
        ],
        AutofillGroup(
          child: Stack(
            alignment: Alignment.center,
            children: [
              IgnorePointer(
                ignoring: !active,
                child: Opacity(
                  opacity: active ? 1.0 : 0.45,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(
                      6,
                      (i) => _otpBox(
                        controllers[i],
                        focusNodes[i],
                        i,
                        controllers,
                        focusNodes,
                        enabled: active,
                      ),
                    ),
                  ),
                ),
              ),
              // Off-screen field for Android/iOS one-time-code autofill.
              Positioned(
                left: -1000,
                width: 1,
                height: 1,
                child: TextField(
                  controller: autofillController,
                  keyboardType: TextInputType.number,
                  autofillHints: const [AutofillHints.oneTimeCode],
                  enableSuggestions: false,
                  autocorrect: false,
                  maxLength: 6,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: const InputDecoration(
                    counterText: '',
                    border: InputBorder.none,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  static Widget _otpBox(
    TextEditingController controller,
    FocusNode focusNode,
    int index,
    List<TextEditingController> allControllers,
    List<FocusNode> allFocusNodes, {
    required bool enabled,
  }) {
    return Container(
      width: 42,
      height: 46,
      margin: const EdgeInsets.symmetric(horizontal: 3),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppTheme.gate2InputFill,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppTheme.gate2BorderSubtle, width: 0.8),
      ),
      child: TextField(
        controller: controller,
        focusNode: focusNode,
        enabled: enabled,
        readOnly: !enabled,
        textAlign: TextAlign.center,
        keyboardType: TextInputType.number,
        maxLength: 1,
        autofillHints:
            index == 0 ? const [AutofillHints.oneTimeCode] : null,
        style: const TextStyle(
          color: AppTheme.gate2TextPrimary,
          fontSize: 18,
          fontWeight: FontWeight.w600,
        ),
        inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        decoration: const InputDecoration(
          counterText: '',
          border: InputBorder.none,
          contentPadding: EdgeInsets.zero,
        ),
        onChanged: (value) {
          if (value.length > 1) {
            final digits = value.replaceAll(RegExp(r'\D'), '');
            for (var i = 0; i < 6; i++) {
              allControllers[i].text = i < digits.length ? digits[i] : '';
            }
            if (digits.length == 6) {
              allFocusNodes[5].unfocus();
            } else if (digits.isNotEmpty) {
              allFocusNodes[digits.length.clamp(0, 5)].requestFocus();
            }
            return;
          }
          if (value.isNotEmpty && index < 5) {
            allFocusNodes[index + 1].requestFocus();
          }
          if (value.isEmpty && index > 0) {
            allFocusNodes[index - 1].requestFocus();
          }
        },
      ),
    );
  }
}
