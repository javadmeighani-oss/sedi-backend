# گزارش باگ‌های شناسایی شده - Sedi Chat App

**تاریخ بررسی:** 2024-12-26  
**منبع:** تصویر UI و بررسی کد

---

## 🐛 باگ‌های شناسایی شده

### 1. ⚠️ **باگ اصلی: پیام تکراری (Duplicate Message)**

**مشکل:**
پیام کاربر "خوشحالم که باهات آشنا شدم. امروز چطوری؟" دو بار در چت نمایش داده می‌شود.

**علت:**
در فایل `chat_controller.dart`، خطوط 315-331:

```dart
// ---------------------------
// Name Collection (natural in conversation - AI-driven)
// ---------------------------
if (conversationState == ConversationState.askingName) {
  await _handleNameCollection(trimmed);
  // Continue to normal chat after name  ← مشکل اینجاست!
}

// ---------------------------
// Normal Chat
// ---------------------------

// 1️⃣ Add user message
messages.add(  ← پیام دوباره اضافه می‌شود!
  ChatMessage(
    text: trimmed,
    isSedi: false,
    isUser: true,
  ),
);
```

**توضیح:**
- وقتی کاربر در حالت `askingName` است و نامش را وارد می‌کند
- `_handleNameCollection` فراخوانی می‌شود
- اما کد ادامه می‌یابد و به بخش "Normal Chat" می‌رود
- در نتیجه پیام کاربر **دوباره** به لیست اضافه می‌شود

**راه حل:**
بعد از `_handleNameCollection` باید `return` اضافه شود:

```dart
if (conversationState == ConversationState.askingName) {
  await _handleNameCollection(trimmed);
  return; // ← اضافه شود
}
```

**اولویت:** 🔴 **بالا** (باگ بحرانی UI)

---

### 2. ⚠️ **مشکل مشابه: Security Password Setup**

**مشکل:**
همین مشکل در `askingSecurityPassword` هم وجود دارد (خط 307-310):

```dart
if (conversationState == ConversationState.askingSecurityPassword) {
  await _handleSecurityPasswordSetup(trimmed);
  return; // ← این return وجود دارد، خوب است
}
```

**وضعیت:** ✅ این مورد درست است (return وجود دارد)

---

### 3. ⚠️ **مشکل مشابه: Security Verification**

**مشکل:**
در `verifyingSecurity` هم همین مشکل وجود دارد (خط 299-302):

```dart
if (conversationState == ConversationState.verifyingSecurity) {
  await _handleSecurityVerification(trimmed);
  return; // ← این return وجود دارد، خوب است
}
```

**وضعیت:** ✅ این مورد درست است (return وجود دارد)

---

## 📋 خلاصه باگ‌ها

| # | باگ | اولویت | وضعیت | فایل |
|---|-----|--------|-------|------|
| 1 | پیام تکراری در حالت `askingName` | 🔴 بالا | ❌ نیاز به fix | `chat_controller.dart:315-318` |
| 2 | Security Password Setup | ✅ | ✅ درست است | `chat_controller.dart:307-310` |
| 3 | Security Verification | ✅ | ✅ درست است | `chat_controller.dart:299-302` |

---

## 🔧 راه حل پیشنهادی

### Fix برای باگ #1:

```dart
// ---------------------------
// Name Collection (natural in conversation - AI-driven)
// ---------------------------
if (conversationState == ConversationState.askingName) {
  await _handleNameCollection(trimmed);
  return; // ← اضافه شود تا از ادامه کد جلوگیری شود
}
```

---

## ✅ بررسی‌های اضافی

### بررسی شده:
- ✅ `_handleSecurityPasswordSetup` - return دارد
- ✅ `_handleSecurityVerification` - return دارد
- ❌ `_handleNameCollection` - return ندارد ← **مشکل**

### نکات:
- در `_handleNameCollection`، پیام کاربر به عنوان نام استفاده می‌شود
- نباید همان متن دوباره به عنوان پیام چت اضافه شود
- باید بعد از `_handleNameCollection` از ادامه کد جلوگیری شود

---

**وضعیت کلی:** 1 باگ بحرانی شناسایی شده که نیاز به fix فوری دارد.

