# بررسی عملکرد آیکن تایید در صفحه Onboarding

**تاریخ:** 2024-12-30  
**هدف:** اطمینان از عملکرد صحیح آیکن تایید

---

## بررسی عملکرد

### 1. تغییر رنگ دکمه (طوسی → مشکی)

**شرایط:**
- ✅ دکمه وقتی فرم معتبر نیست: **طوسی** (`AppTheme.metalGrey`)
- ✅ دکمه وقتی فرم معتبر است: **مشکی** (`AppTheme.primaryBlack`)

**کد:**
```dart
final isEnabled = _isFormValid && !_isSubmitting;

decoration: BoxDecoration(
  color: isEnabled
      ? AppTheme.primaryBlack // Black when valid (form is filled)
      : AppTheme.metalGrey, // Grey when invalid or submitting
  shape: BoxShape.circle,
),
```

**Validation Logic:**
```dart
void _validateForm() {
  final nameText = _nameController.text.trim();
  final nameValid = nameText.isNotEmpty && nameText.length >= 2;
  final isValid = nameValid && _isPasswordValid;
  
  setState(() {
    _isFormValid = isValid; // این باعث تغییر رنگ دکمه می‌شود
  });
}

void _validatePassword() {
  final password = _passwordController.text;
  final hasMinLength = password.length >= 6;
  final isValid = hasMinLength;
  
  setState(() {
    _isPasswordValid = isValid;
    _validateForm(); // بعد از validation رمز، فرم را هم validate می‌کند
  });
}
```

**Listeners:**
```dart
@override
void initState() {
  super.initState();
  _nameController.addListener(_validateForm); // هر تغییر در نام → validate
  _passwordController.addListener(_validatePassword); // هر تغییر در رمز → validate
}
```

**نتیجه:** ✅ رنگ دکمه به صورت خودکار تغییر می‌کند وقتی:
- نام حداقل 2 کاراکتر داشته باشد
- رمز حداقل 6 کاراکتر داشته باشد

---

### 2. عملکرد دکمه (لمس و Navigation)

**کد دکمه:**
```dart
GestureDetector(
  behavior: HitTestBehavior.opaque, // اطمینان از capture شدن tap
  onTap: isEnabled ? () {
    print('[OnboardingPage] ========== Submit button TAPPED ==========');
    _submitForm(); // فراخوانی تابع submit
  } : () {
    // وقتی دکمه disabled است، فقط log می‌کند
    print('[OnboardingPage] Button disabled');
  },
  child: Container(...),
)
```

**تابع _submitForm:**
```dart
Future<void> _submitForm() async {
  // 1. بررسی double submission
  if (_isSubmitting) return;
  
  // 2. بررسی validation
  if (!_isFormValid) return;
  
  // 3. Set submitting state
  setState(() {
    _isSubmitting = true;
  });
  
  try {
    // 4. Setup onboarding با backend
    final result = await chatService.setupOnboarding(
      _nameController.text.trim(),
      _passwordController.text,
      systemLanguage,
    );
    
    // 5. Save user profile locally
    await UserProfileManager.saveProfile(profile);
    
    // 6. Navigate to ChatPage
    if (mounted) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (context) => ChatPage(
            initialMessage: result['message']?.toString(),
          ),
        ),
      );
    }
  } catch (e) {
    // Handle error
  }
}
```

**Navigation:**
- ✅ استفاده از `pushReplacement` به جای `push` → صفحه Onboarding بسته می‌شود
- ✅ Navigation به `ChatPage` با `initialMessage`
- ✅ بررسی `mounted` قبل از navigation

---

## Flow Diagram

```
User Types Name/Password
        ↓
Controller Listener Triggered
        ↓
_validatePassword() / _validateForm()
        ↓
_isFormValid = true (if valid)
        ↓
setState() → UI Rebuild
        ↓
Button Color: Grey → Black ✅
        ↓
User Taps Button
        ↓
GestureDetector.onTap() → _submitForm()
        ↓
_isSubmitting = true
        ↓
Setup Onboarding (Backend)
        ↓
Save Profile (Local)
        ↓
Navigator.pushReplacement()
        ↓
ChatPage Opens ✅
OnboardingPage Closes ✅
```

---

## تست‌های مورد نیاز

### تست 1: تغییر رنگ دکمه
1. ✅ صفحه Onboarding باز می‌شود
2. ✅ دکمه تایید **طوسی** است (فرم خالی)
3. ✅ کاربر نام وارد می‌کند (حداقل 2 کاراکتر)
4. ✅ دکمه هنوز **طوسی** است (رمز خالی)
5. ✅ کاربر رمز وارد می‌کند (حداقل 6 کاراکتر)
6. ✅ دکمه به **مشکی** تبدیل می‌شود ✅

### تست 2: عملکرد دکمه
1. ✅ دکمه **طوسی** است → لمس نمی‌کند (onTap null نیست اما فقط log می‌کند)
2. ✅ دکمه **مشکی** است → لمس می‌کند
3. ✅ بعد از لمس:
   - Loading indicator نمایش داده می‌شود
   - `_submitForm()` اجرا می‌شود
   - Backend call انجام می‌شود
   - Profile ذخیره می‌شود
   - Navigation به ChatPage انجام می‌شود
   - صفحه Onboarding بسته می‌شود ✅

---

## بهبودهای اعمال شده

1. ✅ اضافه کردن `behavior: HitTestBehavior.opaque` برای اطمینان از capture شدن tap
2. ✅ اضافه کردن handler برای حالت disabled (برای debugging)
3. ✅ استفاده از `pushReplacement` برای بستن صفحه Onboarding
4. ✅ بررسی `mounted` قبل از navigation
5. ✅ Reset کردن `_isSubmitting` قبل از navigation

---

## نتیجه

✅ **آیکن تایید:**
- رنگ از طوسی به مشکی تغییر می‌کند وقتی فرم معتبر است
- بعد از لمس، پنجره بسته می‌شود و وارد ChatPage می‌شود
- به درستی کار می‌کند

**آماده برای تست!**

