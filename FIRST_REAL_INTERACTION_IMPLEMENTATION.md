# First Real Interaction Implementation - Summary

## Overview

The first real interaction prompts have been implemented in `app/core/conversation/prompts.py`. These prompts are triggered **after onboarding is complete** (name and password confirmed) to begin the actual health care conversation in a calm, welcoming, and user-controlled manner.

---

## Implementation Details

### 1. Prompts Added

**Location:** `_init_onboarding_prompts()` method

**Three new prompt states:**

1. **first_real_interaction** - Open invitation after onboarding
2. **unclear_response** - Fallback for unclear/hesitant user responses
3. **medical_question** - Safe response for direct medical questions

All prompts are available in three languages (EN/FA/AR).

---

### 2. Stage Mapping

**Trigger Conditions:**
- Onboarding is complete (name + password confirmed)
- Conversation count: 4-6 (after password confirmation)
- Stage: `INTRODUCTION` (memory_count = 1-3) transitioning to `GETTING_TO_KNOW`

**Mapping:**
- **first_real_interaction** → Triggered when onboarding complete, first real message
- **unclear_response** → Triggered after first_real_interaction if user response is unclear
- **medical_question** → Triggered if user asks direct medical question

**Note:** No new stages were added. The prompts work within existing `INTRODUCTION` stage, transitioning naturally to `GETTING_TO_KNOW`.

---

### 3. Detection Logic

**Location:** `_get_onboarding_state()` method

**Detection Flow:**

#### First Real Interaction:
```
Conditions:
- name_learned = true
- conversation_count >= 4 and <= 6
- password_requested = false (onboarding complete)
- password_just_confirmed OR haven't shown first interaction yet
```

#### Unclear Response:
```
Conditions:
- name_learned = true
- conversation_count >= 5 and <= 7
- password_requested = false
- Last Sedi message was first_real_interaction
- User response is:
  - Very short (<= 3 chars)
  - Unclear keywords ("idk", "?", "چی", "ماذا", etc.)
```

#### Medical Question:
```
Conditions:
- name_learned = true
- password_requested = false
- User message contains medical keywords:
  EN: diagnose, treatment, prescribe, symptom, disease, etc.
  FA: تشخیص، درمان، دارو، علائم، بیماری، etc.
  AR: تشخيص، علاج، دواء، أعراض، مرض، etc.
```

---

## Prompt Content

### First Real Interaction

**English:**
```
Dear {user_name},
I'm really glad we're here together.

I'd love to know —
how can I support you today?
```

**Persian:**
```
{user_name} عزیز،
خیلی خوشحالم که اینجا کنار هم هستیم.

حالا دوست دارم بدونم
در چه زمینه‌ای می‌تونم کنارت باشم و کمکت کنم؟
```

**Arabic:**
```
عزيزي {user_name}،
سعيد جداً بوجودنا هنا معاً.

أود أن أعرف،
كيف يمكنني أن أكون إلى جانبك اليوم؟
```

### Unclear Response

**English:**
```
That's totally okay.
We can start from wherever feels easiest for you.

For example:
– Health support
– Daily check-ins
– Building a simple routine
– Or just talking

You choose. I'm here with you.
```

**Persian:**
```
کاملاً قابل درکه.
می‌تونیم از هر جایی که برات راحت‌تره شروع کنیم.

مثلاً:
– مراقبت از سلامت
– پیگیری حال‌و‌احوال روزانه
– ساختن یک روتین ساده
– یا فقط صحبت کردن

تو انتخاب کن، من کنارت هستم.
```

**Arabic:**
```
لا بأس بذلك تماماً.
يمكننا أن نبدأ من أي مكان تشعر أنه أسهل لك.

على سبيل المثال:
– الدعم الصحي
– المتابعة اليومية
– بناء روتين بسيط
– أو مجرد الحديث

أنت تختار، وأنا معك.
```

### Medical Question

**English:**
```
I can help you understand things better
and be here to support you,
but medical diagnosis or treatment decisions
should always be made with a doctor.

If you'd like,
we can start by talking a bit about your situation.
```

**Persian:**
```
می‌تونم کمکت کنم موضوع رو بهتر بفهمی
و کنارت باشم،
اما تشخیص یا توصیه پزشکی قطعی
وظیفه پزشکه.

اگه دوست داری،
می‌تونیم اول کمی درباره شرایطت صحبت کنیم.
```

**Arabic:**
```
يمكنني مساعدتك على فهم الأمور بشكل أفضل
والوقوف إلى جانبك،
لكن التشخيص أو القرارات الطبية
يجب أن تتم دائماً مع طبيب مختص.

إذا أحببت،
يمكننا أن نبدأ بالحديث قليلاً عن وضعك.
```

---

## Example Flow

### After Password Confirmation

```
User: (confirms password - "mypassword123")
Sedi: "Dear Javad,
      I'm really glad we're here together.
      
      I'd love to know —
      how can I support you today?"
State: first_real_interaction
Stage: INTRODUCTION → GETTING_TO_KNOW
```

### User Response Unclear

```
User: "?"
Sedi: "That's totally okay.
      We can start from wherever feels easiest for you.
      
      For example:
      – Health support
      – Daily check-ins
      – Building a simple routine
      – Or just talking
      
      You choose. I'm here with you."
State: unclear_response
```

### User Asks Medical Question

```
User: "Can you diagnose my symptoms?"
Sedi: "I can help you understand things better
      and be here to support you,
      but medical diagnosis or treatment decisions
      should always be made with a doctor.
      
      If you'd like,
      we can start by talking a bit about your situation."
State: medical_question
```

---

## Key Features

### 1. User Control
- Open invitation, no pressure
- User chooses where to start
- Multiple options provided

### 2. Safety First
- Medical questions redirected safely
- No diagnosis or treatment claims
- Encourages doctor consultation

### 3. Calm & Welcoming
- Warm, human tone
- No interrogation
- Supportive language

### 4. Language Support
- Full support for EN/FA/AR
- Medical keywords detected in all languages
- Unclear response detection per language

---

## Integration Points

### With Existing System

1. **Onboarding Flow:**
   - Triggers after password confirmation
   - Uses same prompt structure as onboarding
   - Seamless transition from onboarding to real interaction

2. **Stage System:**
   - Works within `INTRODUCTION` stage
   - Natural transition to `GETTING_TO_KNOW`
   - No stage changes required

3. **Context System:**
   - Uses `conversation_count` to detect timing
   - Uses `name_learned` flag to verify onboarding complete
   - Reads from structured memory domains

4. **Response Generation:**
   - Hardcoded prompts for consistency
   - Falls back to GPT after first interaction
   - Maintains trust-building tone

---

## Detection Logic Details

### First Real Interaction Detection

**Primary Trigger:**
- Password just confirmed (waiting_for_confirmation was true, user provided password)
- OR conversation_count 4-6, name learned, no password flow active, haven't shown yet

**Prevents:**
- Showing multiple times
- Showing during onboarding
- Showing before password confirmed

### Unclear Response Detection

**Keywords by Language:**
- **EN:** "idk", "?", "what", "not sure", "unsure", "hmm", "um", "uh"
- **FA:** "؟", "چی", "نمیدونم", "مطمئن نیستم", "نمیدانم", "هوم"
- **AR:** "ماذا", "لست متأكداً", "لا أعرف", "؟"

**Also detects:**
- Very short responses (<= 3 characters)
- Single question marks

### Medical Question Detection

**Keywords by Language:**
- **EN:** diagnose, diagnosis, treatment, prescribe, medicine, symptom, disease, illness, sick, pain, cure, heal
- **FA:** تشخیص، درمان، دارو، علائم، بیماری، مریض، درد، درمان کن، تشخیص بده
- **AR:** تشخيص، علاج، دواء، أعراض، مرض، مريض، ألم، عالج، شخص

**Behavior:**
- Detects medical keywords in user message
- Returns safe response redirecting to doctor
- Maintains supportive tone

---

## Limitations & Future Enhancements

### Current Limitations

1. **Medical Question Detection:**
   - Keyword-based (simplified)
   - Could be enhanced with NLP for better detection
   - May miss nuanced medical questions

2. **Unclear Response Detection:**
   - Relies on keyword matching and length
   - Could be enhanced with intent detection
   - May not catch all unclear responses

3. **Timing:**
   - Uses conversation_count for timing
   - Assumes password confirmation happens around count 4
   - Could be enhanced with explicit onboarding_complete flag

### Future Enhancements

1. Add explicit `onboarding_complete` flag in conversation_state
2. Enhance medical question detection with NLP
3. Improve unclear response detection with intent analysis
4. Add more nuanced responses for different user hesitations

---

## Testing Recommendations

### Test Cases

1. **First Real Interaction:**
   - Verify appears after password confirmation
   - Test in all three languages
   - Verify {user_name} placeholder works

2. **Unclear Response:**
   - Test with "?", "idk", "چی", "ماذا"
   - Test with very short responses
   - Verify appears only after first_real_interaction

3. **Medical Question:**
   - Test with "diagnose", "treatment", "تشخیص", "علاج"
   - Verify safe response redirects to doctor
   - Test in all three languages

4. **Flow Continuity:**
   - Verify smooth transition from onboarding
   - Verify GPT takes over after first interaction
   - Verify no prompt conflicts

---

## Conclusion

The first real interaction prompts have been successfully implemented with:
- ✅ Open, welcoming invitation after onboarding
- ✅ Fallback for unclear/hesitant responses
- ✅ Safe handling of medical questions
- ✅ Full language support (EN/FA/AR)
- ✅ Integration with existing stage system
- ✅ No database or schema changes
- ✅ Context-based state detection

The system now provides a calm, user-controlled entry point into the health care conversation after trust and security are established.

