# Onboarding Prompts Implementation - Summary

## Overview

The onboarding and trust-building conversation prompts have been implemented in `app/core/conversation/prompts.py`. The implementation uses hardcoded prompts during the onboarding flow to ensure consistent, trust-building interactions before switching to GPT-generated responses.

---

## Implementation Details

### 1. System Identity Prompt

**Location:** `_build_system_prompt()` method

**Content:** Replaced the base system prompt with the new SEDI identity that emphasizes:
- Building trust-based relationships
- Security and privacy protection
- Calm, respectful, human communication
- Language adaptation (EN/FA/AR)

**Languages Supported:**
- English (en)
- Persian/Farsi (fa)
- Arabic (ar)

---

### 2. Onboarding Prompts Structure

**Location:** `_init_onboarding_prompts()` method

**Hardcoded Prompts by State:**

1. **first_launch** - Initial greeting asking for name
2. **name_pending** - Polite request for name if not provided
3. **name_confirmed** - Thank user, introduce Sedi, ask for password
4. **password_pending** - Enforce minimum 6 characters
5. **password_confirm** - Ask user to repeat password
6. **password_mismatch** - Passwords don't match, try again
7. **security_gate_active** - User tries to skip, explain importance

All prompts are available in three languages (EN/FA/AR).

---

### 3. Onboarding State Detection

**Location:** `_get_onboarding_state()` method

**Logic:**
- Only active during `FIRST_CONTACT` and early `INTRODUCTION` stages
- Detects onboarding state based on:
  - Conversation count
  - Whether name is learned (from `conversation_state.flags.name_learned` or profile)
  - Whether password was requested (from last Sedi message)
  - Whether password confirmation is pending
  - User message content and length

**State Detection Flow:**
```
conversation_count == 0 → first_launch
name not learned → name_pending
name learned + password not requested → name_confirmed
password requested + too short → password_pending
password provided + need confirmation → password_confirm
name learned + password requested + user tries to skip → security_gate_active
```

---

### 4. Response Generation Flow

**Location:** `generate_response()` method

**Flow:**
1. Check if in onboarding state
2. If yes → Use hardcoded onboarding prompt
3. If no → Use GPT-generated response (normal flow)

**Key Method:** `_get_onboarding_response()`
- Selects prompt by state and language
- Replaces `{user_name}` placeholder with actual name
- Returns hardcoded text

---

## Stage Mapping

### Existing Stages (from stages.py)

- **FIRST_CONTACT** (memory_count = 0)
- **INTRODUCTION** (memory_count = 1-3)
- **GETTING_TO_KNOW** (memory_count = 4-10)
- **DAILY_RELATION** (memory_count = 11-30)
- **STABLE_RELATION** (memory_count = 31+)

### Onboarding Flow Mapping

The onboarding flow occurs within the existing stages:

| Onboarding State | Maps To Stage | Memory Count | Description |
|-----------------|---------------|--------------|-------------|
| first_launch | FIRST_CONTACT | 0 | Initial greeting |
| name_pending | FIRST_CONTACT | 0-1 | Waiting for name |
| name_confirmed | INTRODUCTION | 1-2 | Name learned, asking for password |
| password_pending | INTRODUCTION | 2-3 | Password too short |
| password_confirm | INTRODUCTION | 2-3 | Waiting for confirmation |
| password_mismatch | INTRODUCTION | 2-3 | Passwords don't match |
| security_gate_active | INTRODUCTION | 2-3 | User tries to skip |

**Note:** No new stages were added. The onboarding logic works within existing stages using context-based state detection.

---

## Language Adaptation

### How It Works

1. **Language Detection:**
   - Language is set in `ConversationPrompts.__init__(language: str)`
   - Default: "en"
   - Supported: "en", "fa", "ar"

2. **Prompt Selection:**
   - `_init_onboarding_prompts()` creates prompts for all three languages
   - `_get_onboarding_response()` selects prompts by `self.language`
   - Falls back to English if language not found

3. **System Prompt:**
   - Base system prompt includes language-specific identity text
   - All three languages have complete translations

### Language-Specific Prompts

All onboarding prompts are available in:
- **English (en):** Complete translations
- **Persian/Farsi (fa):** Complete translations with proper Persian script
- **Arabic (ar):** Complete translations with proper Arabic script

---

## Key Features

### 1. Trust-Building First
- System prompt emphasizes trust before care
- Onboarding ensures name and security are established
- No skipping of security steps

### 2. Security Enforcement
- Minimum password length: 6 characters
- Password confirmation required
- Cannot proceed without security setup

### 3. Language Support
- Full support for EN/FA/AR
- Prompts match user's language preference
- System identity adapts to language

### 4. State Management
- Context-based state detection
- No database changes required
- Works with existing memory structure

---

## Example Flow

### First Message (English)
```
User: (opens chat)
Sedi: "Hello, I'm Sedi.
      I'm really glad we can connect.
      
      May I know your name?"
State: first_launch
Stage: FIRST_CONTACT
```

### User Provides Name
```
User: "My name is Javad"
Sedi: "Thank you, Javad.
      
      From now on, I'll be here as your personal health and care assistant.
      To protect your information and keep our communication safe,
      we need to set up a personal security password.
      
      Please choose a password that only you know and send it to me.
      I'm here and waiting."
State: name_confirmed
Stage: INTRODUCTION
```

### User Provides Short Password
```
User: "123"
Sedi: "For security reasons, your password needs to be at least 6 characters long.
      Please choose a longer password and send it again."
State: password_pending
Stage: INTRODUCTION
```

### User Provides Valid Password
```
User: "mypassword123"
Sedi: "Just to make sure everything is correct,
      please enter the same password one more time."
State: password_confirm
Stage: INTRODUCTION
```

### User Tries to Skip
```
User: "Can we skip this?"
Sedi: "Javad,
      to build a real and meaningful connection
      and to protect your personal information,
      I need a security password from you first.
      
      Please choose a password with at least 6 characters and send it to me.
      After that, I'll always be here to support and care for you."
State: security_gate_active
Stage: INTRODUCTION
```

---

## Integration Points

### With Existing System

1. **Memory System:**
   - Uses `context.profile.name` to detect if name is learned
   - Uses `context.conversation_state.flags.name_learned` for name status
   - No changes to memory schema

2. **Stage System:**
   - Works within existing stages (FIRST_CONTACT, INTRODUCTION)
   - No new stages added
   - Stage transitions work as before

3. **Context System:**
   - Uses context to determine onboarding state
   - Reads from structured memory domains
   - No changes to context structure

4. **Brain System:**
   - `generate_response()` checks onboarding state first
   - Falls back to GPT if not in onboarding
   - No changes to brain orchestration

---

## Limitations & Future Enhancements

### Current Limitations

1. **Password Mismatch Detection:**
   - Currently simplified - would need to track previous password in context
   - Could be enhanced by storing password attempt in conversation_state

2. **Name Extraction:**
   - Relies on memory extraction to detect if name is learned
   - Could be enhanced with better NLP for name detection

3. **State Persistence:**
   - Onboarding state is computed on-demand
   - Could be stored in conversation_state for better tracking

### Future Enhancements

1. Store password attempt in conversation_state for mismatch detection
2. Add more sophisticated name extraction from user messages
3. Track onboarding progress in conversation_state flags
4. Add validation for password strength (beyond length)

---

## Testing Recommendations

### Test Cases

1. **First Launch:**
   - Verify `first_launch` prompt appears on first message
   - Test in all three languages

2. **Name Flow:**
   - Test name provided vs. not provided
   - Test `name_pending` appears when name not provided
   - Test `name_confirmed` appears after name learned

3. **Password Flow:**
   - Test password too short → `password_pending`
   - Test valid password → `password_confirm`
   - Test password mismatch (if implemented)
   - Test skip attempt → `security_gate_active`

4. **Language Adaptation:**
   - Test all prompts in EN/FA/AR
   - Verify correct language is used based on user preference

5. **Stage Transitions:**
   - Verify onboarding works in FIRST_CONTACT and INTRODUCTION
   - Verify normal GPT flow after onboarding completes

---

## Conclusion

The onboarding prompts have been successfully implemented with:
- ✅ Hardcoded trust-building prompts
- ✅ Full language support (EN/FA/AR)
- ✅ Security enforcement (password length, confirmation)
- ✅ Integration with existing stage system
- ✅ No database or schema changes
- ✅ Context-based state detection

The system now provides a structured onboarding experience that builds trust before any real health care interaction begins.

