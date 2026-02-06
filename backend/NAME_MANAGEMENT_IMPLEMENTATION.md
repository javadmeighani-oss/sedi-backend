# پیاده‌سازی مدیریت Name در UserProfile

**تاریخ:** 2024-12-30  
**هدف:** ذخیره name و password در UserProfile و استفاده از name در conversation

---

## 🔍 تغییرات انجام شده

### 1. Backend - دریافت Name از Frontend

**فایل:** `backend/app/routers/interact.py`

**تغییر:**
```python
@router.post("/chat", response_model=InteractionResponse)
def chat_with_sedi(
    message: str = Query(...),
    lang: str = Query("en"),
    user_id: Optional[int] = Query(None),
    name: Optional[str] = Query(None),  # ✅ اضافه شد - name از frontend
    secret_key: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    # ...
    result = brain.process_message(user.id, message, user_name=name)  # ✅ name به brain ارسال می‌شود
```

**نتیجه:** ✅ Backend name را از frontend دریافت می‌کند

---

### 2. Backend - قرار دادن Name در Context

**فایل:** `backend/app/core/conversation/context.py`

**تغییر:**
```python
class ConversationContext:
    def __init__(
        self,
        user_id: int,
        stage: ConversationStage,
        memory: ConversationMemory,
        user_message: Optional[str] = None,
        user_name: Optional[str] = None  # ✅ اضافه شد
    ):
        self.user_name = user_name  # ✅ Name از frontend
    
    def build(self) -> Dict[str, any]:
        # ...
        extracted_name = memory_facts.get("profile", {}).get("name")
        final_user_name = self.user_name or extracted_name  # ✅ اولویت با name از frontend
        
        return {
            "user_name": final_user_name,  # ✅ Name در context قرار می‌گیرد
            # ...
        }
```

**نتیجه:** ✅ Name از frontend در context قرار می‌گیرد و اولویت دارد

---

### 3. Backend - Extract کردن Name از Conversation

**فایل:** `backend/app/core/conversation/brain.py`

**تغییر:**
```python
def process_message(self, user_id: int, user_message: str, user_name: Optional[str] = None) -> Dict[str, any]:
    # ...
    context = ConversationContext(
        user_id=user_id,
        stage=current_stage,
        memory=self.memory,
        user_message=user_message,
        user_name=user_name  # ✅ Name از frontend
    )
    
    # Extract name from conversation if user wants to change it
    detected_name = self._extract_name_from_message(user_id, user_message, current_stage, context_data)
    
    return {
        "message": sedi_response,
        "detected_name": detected_name  # ✅ Name detected به frontend برمی‌گردد
    }
```

**متد جدید:** `_extract_name_from_message`
- ✅ Name را از conversation extract می‌کند
- ✅ اگر کاربر بخواهد name را تغییر دهد، detect می‌کند
- ✅ Name را در response برمی‌گرداند (نه در database)

**نتیجه:** ✅ Backend می‌تواند name را از conversation extract کند

---

### 4. Backend - اضافه کردن detected_name به Response

**فایل:** `backend/app/schemas.py`

**تغییر:**
```python
class InteractionResponse(BaseModel):
    message: str
    language: str
    user_id: Optional[int] = None
    timestamp: datetime
    requires_security_check: Optional[bool] = False
    detected_name: Optional[str] = None  # ✅ اضافه شد
```

**فایل:** `backend/app/routers/interact.py`

**تغییر:**
```python
return InteractionResponse(
    message=result["message"],
    language=result["language"],
    user_id=user.id,
    timestamp=datetime.utcnow(),
    requires_security_check=requires_security_check,
    detected_name=result.get("detected_name")  # ✅ Name detected
)
```

**نتیجه:** ✅ detected_name در response به frontend ارسال می‌شود

---

### 5. Frontend - ارسال Name به Backend

**فایل:** `frontend/lib/features/chat/chat_service.dart`

**تغییر:**
```dart
Future<String> sendMessage(
  String userMessage, {
  String? userName,  // ✅ Name از UserProfile
  // ...
}) async {
  // ...
  if (userName != null && userName.isNotEmpty) {
    queryParams['name'] = userName.trim();  // ✅ Name به backend ارسال می‌شود
  }
  // ...
}
```

**فایل:** `frontend/lib/features/chat/state/chat_controller.dart`

**تغییر:**
```dart
final response = await _chatService.sendMessage(
  trimmed,
  userName: _userProfile.name,  // ✅ Name از UserProfile ارسال می‌شود
  userPassword: _userProfile.securityPassword,
  language: currentLanguage,
  userId: _userProfile.userId,
);
```

**نتیجه:** ✅ Name از UserProfile به backend ارسال می‌شود

---

### 6. Frontend - دریافت و Update کردن Name

**فایل:** `frontend/lib/features/chat/chat_service.dart`

**تغییر:**
```dart
// Backend returns 'detected_name' if name detected from conversation
final detectedName = body['detected_name']?.toString();

// Add detected_name to response string
if (detectedName != null && detectedName.isNotEmpty) {
  responseString = 'DETECTED_NAME:$detectedName|$responseString';
}
```

**فایل:** `frontend/lib/features/chat/state/chat_controller.dart`

**تغییر:**
```dart
// Parse response to extract detected_name
final parsed = _parseResponse(response);
final messageToDisplay = parsed['message'] as String;
final detectedName = parsed['detected_name'] as String?;

// Update UserProfile if name was detected
if (detectedName != null && detectedName.isNotEmpty) {
  _userProfile = _userProfile.copyWith(name: detectedName);
  await UserProfileManager.saveProfile(_userProfile);
}
```

**متد جدید:** `_parseResponse` - Map برمی‌گرداند
```dart
Map<String, dynamic> _parseResponse(String? response) {
  // Extract DETECTED_NAME, USER_ID, and message
  return {
    'message': message,
    'detected_name': detectedName,
    'user_id': userId,
  };
}
```

**نتیجه:** ✅ Name detected از conversation در UserProfile update می‌شود

---

## 📋 Flow کامل

### Onboarding:
```
User Enters Name & Password
        ↓
Name & Password Saved in UserProfile (local storage) ✅
        ↓
Backend API Call (password + language only)
        ↓
Backend Creates User (no name in database)
        ↓
Returns user_id + message
        ↓
Frontend Saves Profile Locally (with name) ✅
        ↓
Navigate to ChatPage
```

### Chat Conversation:
```
User Sends Message
        ↓
Frontend Sends: message + name (from UserProfile) + user_id
        ↓
Backend Receives: name from frontend
        ↓
Backend Uses: name in context (priority) ✅
        ↓
Backend Generates: response with user_name
        ↓
If User Changes Name:
  - Backend Detects: name from conversation
  - Backend Returns: detected_name in response
        ↓
Frontend Receives: detected_name
        ↓
Frontend Updates: UserProfile.name = detected_name ✅
        ↓
Next Message: Uses new name ✅
```

---

## ✅ نتیجه

**Name Management:**
- ✅ Name در UserProfile (local storage) ذخیره می‌شود
- ✅ Name از UserProfile به backend ارسال می‌شود
- ✅ Backend از name در context استفاده می‌کند
- ✅ اگر کاربر name را تغییر دهد، backend آن را detect می‌کند
- ✅ Name جدید در UserProfile update می‌شود
- ✅ از آن به بعد از name جدید استفاده می‌شود

**Password Management:**
- ✅ Password در UserProfile (local storage) ذخیره می‌شود
- ✅ Password برای authentication استفاده می‌شود

---

## 🔄 استفاده از Name

### در Conversation:
- ✅ صدی از name برای خطاب کردن کاربر استفاده می‌کند
- ✅ اگر name وجود نداشته باشد، از "friend" استفاده می‌شود
- ✅ اگر کاربر name را تغییر دهد، از name جدید استفاده می‌شود

### در Context:
- ✅ Name از frontend اولویت دارد
- ✅ اگر name از frontend نباشد، از extracted name استفاده می‌شود
- ✅ اگر هیچ name‌ای نباشد، از "friend" استفاده می‌شود

---

**وضعیت:** ✅ **تمام تغییرات انجام شد**

**نکته:** Backend باید restart شود تا تغییرات اعمال شود.

