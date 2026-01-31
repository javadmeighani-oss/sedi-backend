# Conversation Brain v1 - Architecture Documentation

## Purpose

The Conversation Brain v1 is the foundation for human-like conversation in Sedi. It implements a structured, stage-based conversation system that builds long-term relationships with users through natural dialogue.

**Key Principle:** Conversation is the PRIMARY mechanism for understanding users, building relationships, learning lifestyle and preferences, and providing future health guidance.

## Architecture Overview

The Conversation Brain follows a strict separation of responsibilities:

```
Frontend (Passive)
    ↓ API Request
Router (Thin Layer)
    ↓
Brain (COMMANDER)
    ↓
├── Stages (State Machine)
├── Memory (Read/Write)
├── Context (Builder)
└── Prompts (Text Generation)
```

## File Responsibilities

### `brain.py` - Central Decision Engine (COMMANDER)

**Responsibility:**
- Entry point for all chat interactions
- Receives: `user_id`, `user_message`
- Determines current conversation stage
- Requests text from `prompts.py`
- Updates memory via `memory.py`
- Returns assistant message + metadata

**What it does NOT do:**
- NO database queries directly (uses Memory class)
- NO hardcoded text (uses Prompts class)
- NO state machine logic (uses Stages class)

### `stages.py` - Conversation State Machine

**Responsibility:**
- Defines relationship and conversation stages:
  - `FIRST_CONTACT`: User just started, no memory
  - `INTRODUCTION`: Learning name, basic info (1-3 conversations)
  - `GETTING_TO_KNOW`: Learning interests, preferences (4-10 conversations)
  - `DAILY_RELATION`: Established relationship, regular check-ins (11-30 conversations)
  - `STABLE_RELATION`: Long-term companion, deep understanding (30+ conversations)
- Handles stage transitions only

**What it does NOT do:**
- NO text generation
- NO database access (receives Session, queries only for stage determination)

### `prompts.py` - Sedi's Voice

**Responsibility:**
- Generates ALL assistant texts:
  - Greetings
  - Questions
  - Follow-ups
- Uses context only
- Uses GPT-4o-mini for natural text generation
- Supports multiple languages (en, fa, ar)

**What it does NOT do:**
- NO state changes
- NO database access
- NO decision making

### `memory.py` - Conversation Memory

**Responsibility:**
- Reads/writes conversation memory
- Extracts: name, interests, dislikes, lifestyle hints, identification phrase
- Provides memory facts to context builder

**What it does NOT do:**
- NO decisions
- NO text generation

### `context.py` - Context Builder

**Responsibility:**
- Builds conversation context by combining:
  - Memory
  - Current stage
  - Recent messages
- Provides clean input to brain and prompts

**What it does NOT do:**
- NO decisions
- NO text generation
- NO database access (receives Memory instance)

### `routers/interact.py` - Thin API Layer

**Responsibility:**
- Receives API request
- Calls Conversation Brain
- Returns response
- Handles authentication

**What it does NOT do:**
- NO logic
- NO decisions
- NO text generation

## Conversation Flow

### 1. User Sends Message

```
Frontend → POST /interact/chat
  Parameters:
    - message: "Hello"
    - name: "John"
    - secret_key: "xxx"
    - lang: "en"
```

### 2. Router Receives Request

```python
# routers/interact.py
brain = ConversationBrain(db, language=lang)
result = brain.process_message(user.id, message)
```

### 3. Brain Processes Message

```python
# brain.py
1. Get current stage (stages.py)
2. Build context (context.py)
3. Generate response (prompts.py)
4. Save to memory (memory.py)
5. Check stage transition (stages.py)
6. Return response
```

### 4. Response Sent to Frontend

```json
{
  "message": "Hello John! How are you doing today? 🌿",
  "language": "en",
  "user_id": 1,
  "timestamp": "2025-12-26T10:00:00Z",
  "requires_security_check": false
}
```

## Stage Progression

Stages progress based on conversation count:

- **0 conversations** → `FIRST_CONTACT`
- **1-3 conversations** → `INTRODUCTION`
- **4-10 conversations** → `GETTING_TO_KNOW`
- **11-30 conversations** → `DAILY_RELATION`
- **30+ conversations** → `STABLE_RELATION`

Stages only progress forward (no regression).

## Frontend-Backend Communication

### Frontend Responsibilities

- Sends user message
- Receives assistant message
- Renders message + metadata
- Does NOT know:
  - Conversation stage
  - Relationship state
  - Why a question is asked

### Backend Responsibilities

- Maintains conversation state
- Decides conversation flow
- Generates all texts
- Updates memory and profile

### API Contract

**Request:**
```json
POST /interact/chat
{
  "message": "string",
  "name": "string",
  "secret_key": "string",
  "lang": "en" | "fa" | "ar"
}
```

**Response:**
```json
{
  "message": "string",
  "language": "string",
  "user_id": int,
  "timestamp": "ISO 8601",
  "requires_security_check": boolean
}
```

## What is NOT Implemented (By Design)

The following features are intentionally NOT implemented in v1:

- **Full AI personality tuning**: Basic personality exists, but advanced tuning is for later phases
- **Emotional modeling**: Emotional understanding is not yet implemented
- **Predictive health logic**: Health predictions belong to later phases
- **Notification sending logic**: Notifications are separate from conversation
- **Push notification integration**: Not part of conversation brain

These belong to later phases and will be added incrementally.

## Guarantees

### Responsibility Separation

- Each file has ONE clear responsibility
- No overlapping responsibilities
- Clear boundaries between components

### Text Generation

- ALL conversation texts originate from BACKEND
- Frontend contains NO hardcoded onboarding text
- All text generation uses GPT with context-aware prompts

### State Management

- Conversation state managed by `stages.py`
- Memory managed by `memory.py`
- No state duplication

### Database Access

- Only `memory.py` and `stages.py` access database directly
- Other components receive data through interfaces

## Future Extensions

The architecture is designed to support future additions:

1. **Advanced Memory Extraction**: NLP-based fact extraction from conversations
2. **Emotional Modeling**: Track and respond to user emotions
3. **Personality Adaptation**: Adjust Sedi's personality based on user preferences
4. **Health Context Integration**: Use health data to inform conversations
5. **Multi-turn Context**: Better handling of complex multi-turn conversations

All extensions will maintain the strict responsibility separation.

## Testing

To test the Conversation Brain:

1. Create a user via `/interact/introduce`
2. Send messages via `/interact/chat`
3. Observe stage progression as conversation count increases
4. Verify memory is saved correctly
5. Check that responses are context-aware

## Conclusion

The Conversation Brain v1 provides a solid foundation for human-like conversation in Sedi. It enforces strict separation of responsibilities, ensures all text comes from the backend, and maintains conversation state across interactions.

This architecture is designed to scale and support future enhancements while maintaining code clarity and maintainability.

