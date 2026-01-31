# نمای شماتیک Layout صفحه Onboarding

**تاریخ:** 2024-12-30  
**هدف:** نمایش دقیق ساختار layout و موقعیت آیکن تایید

---

## ساختار Layout (از بالا به پایین)

```
┌─────────────────────────────────────────┐
│         SafeArea (Scaffold Body)         │
│                                           │
│  ┌───────────────────────────────────┐  │
│  │      Column (Main Container)       │  │
│  │                                     │  │
│  │  ┌─────────────────────────────┐   │  │
│  │  │   SediHeader (Logo)          │   │  │
│  │  │   Padding: top: 20, bottom: 16│   │  │
│  │  └─────────────────────────────┘   │  │
│  │                                     │  │
│  │  ┌─────────────────────────────┐   │  │
│  │  │   Expanded (Form Container) │   │  │
│  │  │   ┌───────────────────────┐ │   │  │
│  │  │   │   Center              │ │   │  │
│  │  │   │   ┌─────────────────┐ │ │   │  │
│  │  │   │   │ Container       │ │ │   │  │
│  │  │   │   │ Width: 90%      │ │ │   │  │
│  │  │   │   │ Height: 320px   │ │ │   │  │
│  │  │   │   │ (FIXED)         │ │ │   │  │
│  │  │   │   │                 │ │ │   │  │
│  │  │   │   │ ┌─────────────┐ │ │ │   │  │
│  │  │   │   │ │ Padding: 16 │ │ │ │   │  │
│  │  │   │   │ │             │ │ │ │   │  │
│  │  │   │   │ │ ┌─────────┐ │ │ │ │   │  │
│  │  │   │   │ │ │ Form    │ │ │ │ │   │  │
│  │  │   │   │ │ │         │ │ │ │ │   │  │
│  │  │   │   │ │ │ Column  │ │ │ │ │   │  │
│  │  │   │   │ │ │         │ │ │ │ │   │  │
│  │  │   │   │ │ │ ┌─────┐ │ │ │ │ │   │  │
│  │  │   │   │ │ │ │Name│ │ │ │ │ │   │  │
│  │  │   │   │ │ │ │Field│ │ │ │ │ │   │  │
│  │  │   │   │ │ │ └─────┘ │ │ │ │ │   │  │
│  │  │   │   │ │ │         │ │ │ │ │   │  │
│  │  │   │   │ │ │ SizedBox│ │ │ │ │   │  │
│  │  │   │   │ │ │ (12px)  │ │ │ │ │   │  │
│  │  │   │   │ │ │         │ │ │ │ │   │  │
│  │  │   │   │ │ │ ┌─────┐ │ │ │ │ │   │  │
│  │  │   │   │ │ │ │Pass │ │ │ │ │ │   │  │
│  │  │   │   │ │ │ │Field│ │ │ │ │ │   │  │
│  │  │   │   │ │ │ └─────┘ │ │ │ │ │   │  │
│  │  │   │   │ │ │         │ │ │ │ │   │  │
│  │  │   │   │ │ │         │ │ │ │ │   │  │
│  │  │   │   │ │ │ Spacer()│ │ │ │ │   │  │
│  │  │   │   │ │ │ (pushes │ │ │ │ │   │  │
│  │  │   │   │ │ │ button │ │ │ │ │   │  │
│  │  │   │   │ │ │ down)  │ │ │ │ │   │  │
│  │  │   │   │ │ │         │ │ │ │ │   │  │
│  │  │   │   │ │ │ ┌─────┐ │ │ │ │ │   │  │
│  │  │   │   │ │ │ │ ✓   │ │ │ │ │ │   │  │
│  │  │   │   │ │ │ │Button│ │ │ │ │ │   │  │
│  │  │   │   │ │ │ │(58px)│ │ │ │ │ │   │  │
│  │  │   │   │ │ │ └─────┘ │ │ │ │ │   │  │
│  │  │   │   │ │ │         │ │ │ │ │   │  │
│  │  │   │   │ │ │ SizedBox│ │ │ │ │   │  │
│  │  │   │   │ │ │ (8px)   │ │ │ │ │   │  │
│  │  │   │   │ │ └─────────┘ │ │ │ │   │  │
│  │  │   │   │ └─────────────┘ │ │ │   │  │
│  │  │   │   └─────────────────┘ │ │   │  │
│  │  │   └───────────────────────┘ │   │  │
│  │  └─────────────────────────────┘   │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

---

## جزئیات مهم

### 1. Container (پنجره یوزر نیم)
- **Width:** 90% از عرض صفحه
- **Height:** 320px (ثابت - تغییر نمی‌کند)
- **Background:** `AppTheme.metalGrey.withOpacity(0.3)` (طوسی شفاف)
- **Border Radius:** `AppTheme.radiusMedium` (14px)
- **Padding:** 16px از همه طرف

### 2. Column داخل Form
- **mainAxisSize:** `MainAxisSize.max` (تمام ارتفاع را می‌گیرد)
- **crossAxisAlignment:** `CrossAxisAlignment.center` (وسط افقی)
- **Children:**
  1. Name Field
  2. SizedBox(height: 12)
  3. Password Field
  4. **Spacer()** ← این دکمه را به پایین می‌فرستد
  5. Submit Button
  6. SizedBox(height: 8)

### 3. آیکن تایید (Submit Button)
- **Position:** پایین و وسط (با استفاده از Spacer)
- **Size:** 58px × 58px (دایره)
- **Icon Size:** 34px
- **Color:** 
  - فعال: `AppTheme.primaryBlack` (مشکی)
  - غیرفعال: `AppTheme.metalGrey` (خاکستری)
- **Inside Container:** ✅ بله - داخل Container با padding 16px

---

## محاسبه موقعیت دکمه

```
Container Height: 320px
Padding Top: 16px
Padding Bottom: 16px
Available Height: 320 - 32 = 288px

Name Field: ~60px (label + input + padding)
SizedBox: 12px
Password Field: ~60px (label + input + padding)
Spacer: (288 - 60 - 12 - 60 - 58 - 8) = 90px (فاصله خودکار)
Button: 58px
SizedBox: 8px

Total: 60 + 12 + 60 + 90 + 58 + 8 = 288px ✅
```

---

## اطمینان از قرارگیری دکمه

### ✅ دکمه داخل Container است
- Container دارای `height: 320px` (ثابت)
- Padding: 16px از همه طرف
- دکمه در Column داخل Form داخل Padding داخل Container است

### ✅ دکمه در پایین است
- استفاده از `Spacer()` که تمام فضا را پر می‌کند
- دکمه بعد از Spacer قرار دارد
- `SizedBox(height: 8)` در پایین برای فاصله

### ✅ دکمه در وسط افقی است
- `crossAxisAlignment: CrossAxisAlignment.center`
- دکمه در Column با center alignment

---

## نتیجه

✅ **آیکن تایید:**
- داخل پنجره یوزر نیم است
- در پایین قرار دارد (با استفاده از Spacer)
- در وسط افقی قرار دارد (با استفاده از CrossAxisAlignment.center)
- دارای padding مناسب از پایین (8px)

---

## کد مربوطه

```dart
Container(
  width: containerWidth,
  height: containerHeight, // 320px - FIXED
  decoration: BoxDecoration(...),
  child: Padding(
    padding: const EdgeInsets.all(16),
    child: Form(
      child: Column(
        mainAxisSize: MainAxisSize.max,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          _buildNameSection(),
          const SizedBox(height: 12),
          _buildPasswordSection(),
          const Spacer(), // ← Pushes button to bottom
          _buildSubmitButton(), // ← Button at bottom center
          const SizedBox(height: 8),
        ],
      ),
    ),
  ),
)
```

