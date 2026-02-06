# Experience Stability Layer - Analysis & Design

## STEP 1 – ANALYSIS

### File-by-File Analysis

---

### 1. `interact.py` - User ID Lifecycle

**Current Responsibility:**
- Receives API requests
- Manages user identification (user_id, name/secret_key, or creates anonymous)
- Calls ConversationBrain
- Returns response with user_id

**Experience Stability Issues:**

1. **Anonymous User Creation Logic (Lines 140-160):**
   - Creates NEW anonymous user if no user_id provided
   - Uses UUID to ensure uniqueness - always creates new
   - **PROBLEM:** If frontend doesn't send user_id (even temporarily), new user is created
   - **RESULT:** Conversation resets, memory fragments

2. **User Identification Priority:**
   - Priority 1: user_id (if provided)
   - Priority 2: name/secret_key
   - Priority 3: Create anonymous
   - **ISSUE:** No persistence mechanism for anonymous users across sessions
   - **RESULT:** Each session without user_id = new user = conversation reset

3. **No User Session Tracking:**
   - No device_id or session_id tracking
   - Cannot recover user_id from device fingerprint
   - **RESULT:** Cannot maintain continuity if frontend loses user_id

**Root Cause of Conversation Reset:**
- If frontend doesn't send user_id → new anonymous user created → memory_count = 0 → stage = FIRST_CONTACT → conversation resets

---

### 2. `memory.py` - Persistence & Structure

**Current Responsibility:**
- Reads/writes conversation memory
- Extracts facts from memory using keyword matching
- Manages conversation count and time calculations

**Experience Stability Issues:**

1. **Raw Chat Storage (Lines 170-198):**
   - Memory stored as raw text: `user_message`, `sedi_response`
   - No structured domains (profile, medical, vitals, lifestyle, etc.)
   - **PROBLEM:** Facts are extracted on-demand via keyword matching
   - **RESULT:** Inefficient, error-prone, not RAG-ready

2. **Keyword-Based Extraction (Lines 46-168):**
   - `extract_memory_facts()` uses simple keyword matching
   - No structured storage of facts
   - Facts are computed each time, not stored
   - **PROBLEM:** Facts can be inconsistent, incomplete
   - **RESULT:** System doesn't "remember" structured information reliably

3. **No Structured Memory Domains:**
   - No separation of: profile, medical, vitals, lifestyle, preferences, routines, goals
   - Everything is in raw chat format
   - **PROBLEM:** Cannot query specific domains for RAG
   - **RESULT:** Not RAG-ready

4. **Memory Count Calculation (Line 200-202):**
   - Uses `db.query(Memory).filter(Memory.user_id == user_id).count()`
   - **ISSUE:** If user_id changes, count is wrong
   - **RESULT:** Stage calculation is wrong

**Root Cause of Repetition:**
- Facts are extracted on-demand, not stored
- No structured memory = GPT doesn't have reliable context
- Keyword matching misses information = incomplete context = repeated questions

---

### 3. `stages.py` - Stage Progression

**Current Responsibility:**
- Determines current conversation stage based on memory_count
- Handles stage transitions (forward-only)

**Experience Stability Issues:**

1. **Stage Calculation Timing (Lines 27-58):**
   - `get_stage()` uses `memory_count` from database
   - **ISSUE:** If called BEFORE save, uses old count
   - **ISSUE:** If user_id changes, count is wrong
   - **RESULT:** Stage can be incorrect

2. **Transition Logic (Lines 61-91):**
   - Only allows forward progression (good)
   - But if memory_count is wrong, transition is wrong
   - **PROBLEM:** No validation that stage matches actual memory state
   - **RESULT:** Stage can regress if user_id changes

3. **No Stage Persistence:**
   - Stage is calculated each time, not stored
   - **ISSUE:** If calculation is wrong, stage is wrong
   - **RESULT:** Stage can be inconsistent

**Root Cause of Stage Issues:**
- Stage depends on memory_count
- If memory_count is wrong (user_id change) → stage is wrong
- If stage is wrong → wrong prompts → wrong behavior

---

### 4. `brain.py` - Orchestration Order

**Current Responsibility:**
- Orchestrates conversation processing
- Coordinates: stage → context → prompts → memory → transition

**Experience Stability Issues:**

1. **Orchestration Order (Lines 37-131):**
   ```
   Current order:
   1. get_stage() - uses OLD memory_count
   2. build context() - uses OLD memory_count
   3. generate response()
   4. save_conversation() - updates memory_count
   5. transition_stage() - uses NEW memory_count
   ```
   - **PROBLEM:** Context is built with OLD memory_count
   - **PROBLEM:** Stage used for context is OLD stage
   - **RESULT:** Context doesn't reflect current state

2. **Stage-Stage Mismatch:**
   - Context uses `current_stage` (from step 1)
   - But after save, stage might have changed
   - **PROBLEM:** Response is generated with old stage context
   - **RESULT:** Response doesn't match actual stage

3. **No Validation:**
   - No check that user_id is consistent
   - No check that memory_count matches stage
   - **RESULT:** Inconsistencies can accumulate

**Root Cause of Orchestration Issues:**
- Context built BEFORE save → uses old state
- Response generated with old state → doesn't match new state
- Stage transition happens AFTER response → response is for wrong stage

---

### 5. `context.py` - What the Model Sees

**Current Responsibility:**
- Builds conversation context for GPT
- Combines: memory facts, recent messages, health data, lifestyle patterns

**Experience Stability Issues:**

1. **Context Building (Lines 39-94):**
   - Builds context from memory
   - **ISSUE:** If memory is incomplete (user_id changed), context is incomplete
   - **ISSUE:** Facts are extracted on-demand, not stored
   - **RESULT:** Context can be inconsistent

2. **Memory Facts Extraction (Line 63):**
   - Calls `memory.extract_memory_facts()` which uses keyword matching
   - **PROBLEM:** Facts are computed, not stored
   - **PROBLEM:** Keyword matching is unreliable
   - **RESULT:** Context has incomplete/inconsistent facts

3. **No Structured Context:**
   - Context is a flat dict, not organized by domains
   - **PROBLEM:** GPT doesn't see structured information
   - **RESULT:** Cannot leverage structured memory for RAG

**Root Cause of Context Issues:**
- Context built from raw memory + keyword extraction
- No structured storage = inconsistent extraction
- Incomplete context = GPT gives incomplete responses

---

## STEP 2 – DESIGN

### Experience Stability Layer Design

---

### 1. Memory Domains (Structured Storage)

**Design:**
Store structured facts in memory extraction, organized by domains:

```python
memory_domains = {
    "profile": {
        "name": str,
        "age": int | None,
        "language": str,
        "created_at": datetime
    },
    "medical": {
        "conditions": List[str],
        "medications": List[str],
        "allergies": List[str],
        "health_concerns": List[str]
    },
    "vitals": {
        "heart_rate_avg": float | None,
        "temperature_avg": float | None,
        "spo2_avg": float | None,
        "last_reading": datetime | None
    },
    "lifestyle": {
        "work_patterns": Dict,
        "exercise_patterns": Dict,
        "sleep_patterns": Dict,
        "diet_patterns": Dict
    },
    "preferences": {
        "communication_style": str,
        "health_goals": List[str],
        "interests": List[str]
    },
    "routines": {
        "daily_routine": List[str],
        "weekly_patterns": Dict
    },
    "goals": {
        "health_goals": List[str],
        "fitness_goals": List[str],
        "lifestyle_goals": List[str]
    },
    "conversation_state": {
        "stage": str,
        "last_stage_transition": datetime | None,
        "flags": Dict[str, bool]  # e.g., "name_learned": True
    }
}
```

**Implementation:**
- Store facts as JSON in memory extraction (computed once, cached)
- Update facts incrementally as new information arrives
- Use existing Memory table (no schema change)
- Store structured facts in `extract_memory_facts()` result

---

### 2. Strict Orchestration Order

**Design:**
```
identify → load → process → update → save → respond
```

**Detailed Flow:**
1. **IDENTIFY:** Ensure user_id is stable (no new user creation if user_id provided)
2. **LOAD:** Load existing memory and structured facts
3. **PROCESS:** Build context with CURRENT state (after load, before save)
4. **UPDATE:** Update structured facts with new information
5. **SAVE:** Save conversation + update structured facts
6. **RESPOND:** Return response with correct stage

**Key Change:**
- Move `save_conversation()` to BEFORE context building
- But wait - that's wrong. We need to:
  - Load existing state
  - Build context with existing state
  - Generate response
  - Save new exchange
  - Update stage

**Correct Order:**
```
1. IDENTIFY: user_id (ensure stable)
2. LOAD: existing memory, facts, stage
3. BUILD CONTEXT: with loaded state
4. GENERATE: response with context
5. UPDATE: structured facts with new info
6. SAVE: conversation + facts
7. TRANSITION: stage (if needed)
8. RESPOND: with correct stage
```

---

### 3. Stage Rules to Prevent Loops

**Design:**
1. **Forward-Only Progression:**
   - Stage can only move forward
   - Once in a stage, cannot go back
   - Exception: If user_id changes (shouldn't happen), reset to FIRST_CONTACT

2. **Stage Validation:**
   - Validate that stage matches memory_count
   - If mismatch, use higher stage (never regress)

3. **Stage Persistence:**
   - Store current stage in conversation_state domain
   - Use stored stage if available, otherwise calculate

4. **Transition Rules:**
   - FIRST_CONTACT → INTRODUCTION: memory_count >= 1
   - INTRODUCTION → GETTING_TO_KNOW: memory_count >= 4
   - GETTING_TO_KNOW → DAILY_RELATION: memory_count >= 11
   - DAILY_RELATION → STABLE_RELATION: memory_count >= 31

---

### 4. User ID Stability

**Design:**
1. **Backend Robustness:**
   - If user_id provided, use it (don't create new)
   - If user_id invalid, return error (don't create new)
   - Only create anonymous user if NO user_id AND NO credentials

2. **User Recovery:**
   - Store user_id in response (already done)
   - Frontend must persist user_id (already done)
   - Backend validates user_id exists before use

3. **Anonymous User Handling:**
   - Anonymous users are temporary
   - Should be upgraded to registered users
   - Until upgrade, maintain same user_id

---

## STEP 3 – IMPLEMENTATION PLAN

### Minimal Changes Required

**Files to Modify:**
1. `interact.py` - User ID validation
2. `memory.py` - Structured facts storage
3. `brain.py` - Orchestration order fix
4. `stages.py` - Stage validation
5. `context.py` - Structured context building

**No Changes:**
- DB schema (use existing Memory table)
- API contracts (preserve existing)
- Frontend behavior (already fixed)

---

## STEP 4 – VERIFICATION CHECKLIST

### Experience Stability Verification

**1. User ID Persistence:**
- [ ] Same user_id returned in every response
- [ ] Frontend sends user_id in every request
- [ ] Backend uses same user_id (no new user creation)
- [ ] Anonymous user maintains same user_id across sessions

**2. Memory Load/Save Correctness:**
- [ ] Memory saved after each exchange
- [ ] Memory loaded correctly for next exchange
- [ ] Structured facts updated incrementally
- [ ] Memory count increases correctly

**3. Stage Progression:**
- [ ] Stage progresses forward only
- [ ] Stage matches memory_count
- [ ] Stage transition happens at correct thresholds
- [ ] No stage regression

**4. No Repeated Questions:**
- [ ] GPT sees conversation history
- [ ] GPT sees structured facts
- [ ] GPT doesn't ask same question twice
- [ ] Context includes all relevant information

---

## Example Flow

### First Message from User
```
Request: POST /interact/chat?message=hello&lang=en
Backend: Creates anonymous user (user_id=5)
Response: { "user_id": 5, "message": "Hello! I'm Sedi...", "stage": "first_contact" }
Memory: Saved (count=1)
Stage: FIRST_CONTACT
```

### Second Message
```
Request: POST /interact/chat?message=my name is javad&user_id=5&lang=en
Backend: Uses user_id=5 (same user)
Response: { "user_id": 5, "message": "Nice to meet you, Javad!...", "stage": "introduction" }
Memory: Saved (count=2)
Structured Facts: { "profile": { "name": "javad" } }
Stage: INTRODUCTION (progressed from FIRST_CONTACT)
```

### Third Message
```
Request: POST /interact/chat?message=how are you&user_id=5&lang=en
Backend: Uses user_id=5 (same user)
Response: { "user_id": 5, "message": "I'm doing well, Javad!...", "stage": "introduction" }
Memory: Saved (count=3)
Structured Facts: { "profile": { "name": "javad" } } (unchanged)
Stage: INTRODUCTION (still, needs 4 for next stage)
Context: Includes name "javad" from structured facts
```

**Expected Difference:**
- User ID stays same (5)
- Memory count increases (1 → 2 → 3)
- Stage progresses (FIRST_CONTACT → INTRODUCTION)
- Structured facts accumulate (name learned)
- No repeated questions (GPT sees history + facts)

---

## Success Criteria

✅ **Conversation does not reset:**
- Same user_id across requests
- Memory persists
- Stage doesn't regress

✅ **Stage progresses deterministically:**
- Stage based on memory_count
- Forward-only progression
- Correct thresholds

✅ **Memory persists across requests:**
- Memory saved correctly
- Memory loaded correctly
- Structured facts updated

✅ **System is RAG-ready:**
- Structured memory domains defined
- Facts stored in organized format
- Ready for RAG integration

✅ **No personality/prompt changes:**
- Only stability fixes
- No tone/personality modifications
- No prompt wording changes

