# نقشه راه پیاده‌سازی RAG و Prompt Engineering برای Sedi

## 📋 خلاصه

این سند توضیح می‌دهد چگونه می‌توان از **RAG (Retrieval-Augmented Generation)** و **Prompt Engineering** برای بهبود تعامل و گفتگوی Sedi استفاده کرد.

---

## 🔍 RAG چیست؟

**RAG (Retrieval-Augmented Generation)** یک تکنیک است که:
1. **Retrieval (بازیابی)**: اطلاعات مرتبط را از حافظه/دیتابیس بازیابی می‌کند
2. **Augmentation (افزودن)**: این اطلاعات را به prompt اضافه می‌کند
3. **Generation (تولید)**: GPT با این اطلاعات غنی‌شده پاسخ بهتری تولید می‌کند

### چرا RAG برای Sedi مهم است؟

**مشکل فعلی:**
- Sedi فقط از `recent_messages` (آخرین 5-10 exchange) استفاده می‌کند
- اطلاعات قدیمی‌تر (MEDIUM-TERM و LONG-TERM memory) به درستی استفاده نمی‌شوند
- Keyword-based extraction محدود است و context کامل را نمی‌گیرد

**راه‌حل RAG:**
- تمام تاریخچه گفتگو را در vector database ذخیره می‌کنیم
- بر اساس query کاربر، مرتبط‌ترین اطلاعات را بازیابی می‌کنیم
- این اطلاعات را به prompt اضافه می‌کنیم
- GPT با context کامل‌تر پاسخ بهتری می‌دهد

---

## 🏗️ معماری پیشنهادی

```
User Message
    ↓
[Query Understanding] → Extract intent, entities
    ↓
[Vector Search] → Find relevant memories (semantic search)
    ↓
[Reranking] → Rank by relevance (optional)
    ↓
[Context Building] → Combine: recent + retrieved + health data
    ↓
[Prompt Engineering] → Build comprehensive prompt
    ↓
[GPT Generation] → Generate response with full context
    ↓
[Response] → Return to user
```

---

## 📁 فایل‌های جدید مورد نیاز

### 1. `backend/app/core/conversation/rag/__init__.py`
**مسئولیت:** Package initialization برای RAG module

### 2. `backend/app/core/conversation/rag/embeddings.py`
**مسئولیت:** 
- تولید embeddings برای متن‌ها
- استفاده از OpenAI Embeddings API یا model محلی
- تبدیل متن به vector

**توابع کلیدی:**
```python
def generate_embedding(text: str) -> List[float]
def generate_embeddings_batch(texts: List[str]) -> List[List[float]]
```

### 3. `backend/app/core/conversation/rag/vector_store.py`
**مسئولیت:**
- ذخیره و بازیابی embeddings
- Vector similarity search
- مدیریت vector database

**گزینه‌های پیاده‌سازی:**
- **Option 1: PostgreSQL + pgvector** (پیشنهادی - یکپارچه با دیتابیس موجود)
- **Option 2: ChromaDB** (سبک و سریع)
- **Option 3: FAISS** (محلی، بدون نیاز به دیتابیس)

**توابع کلیدی:**
```python
def store_memory_embedding(user_id: int, memory_id: int, embedding: List[float], text: str)
def search_similar_memories(user_id: int, query_embedding: List[float], limit: int) -> List[Dict]
def update_memory_embedding(memory_id: int, embedding: List[float])
```

### 4. `backend/app/core/conversation/rag/retriever.py`
**مسئولیت:**
- بازیابی اطلاعات مرتبط از vector store
- ترکیب SHORT-TERM, MEDIUM-TERM, LONG-TERM memory
- Reranking نتایج (optional)

**توابع کلیدی:**
```python
def retrieve_relevant_memories(user_id: int, query: str, memory_type: str) -> List[Dict]
def retrieve_by_timeframe(user_id: int, query: str, days: int) -> List[Dict]
def retrieve_by_topic(user_id: int, query: str, topics: List[str]) -> List[Dict]
```

### 5. `backend/app/core/conversation/rag/reranker.py` (Optional)
**مسئولیت:**
- Rerank نتایج retrieval بر اساس relevance
- استفاده از cross-encoder model

**توابع کلیدی:**
```python
def rerank(query: str, candidates: List[Dict]) -> List[Dict]
```

### 6. `backend/app/core/conversation/prompt_builder.py`
**مسئولیت:**
- ساخت prompt بهینه با استفاده از RAG results
- ترکیب: system prompt + retrieved context + conversation history
- Prompt engineering best practices

**توابع کلیدی:**
```python
def build_rag_prompt(
    system_prompt: str,
    retrieved_memories: List[Dict],
    conversation_history: List[Dict],
    user_message: str,
    health_data: Optional[Dict]
) -> List[Dict]
```

---

## 🔄 فایل‌های موجود که باید بازنویسی شوند

### 1. `backend/app/core/conversation/memory.py` ⚠️ **بازنویسی کامل**

**تغییرات:**
- افزودن تابع برای ذخیره embeddings هنگام save_conversation
- افزودن تابع برای بازیابی با RAG
- حفظ backward compatibility با متدهای موجود

**توابع جدید:**
```python
def save_conversation_with_embedding(...)  # Save + generate embedding
def retrieve_semantic_memories(user_id: int, query: str) -> List[Memory]  # RAG retrieval
```

### 2. `backend/app/core/conversation/context.py` ⚠️ **بازنویسی جزئی**

**تغییرات:**
- استفاده از RAG retriever به جای فقط recent_messages
- ترکیب semantic search results با recent messages
- افزودن retrieved_context به context dict

**تغییرات:**
```python
def build(self) -> Dict[str, any]:
    # ... existing code ...
    
    # NEW: RAG retrieval
    if self.user_message:
        retrieved_memories = self.memory.retrieve_semantic_memories(
            self.user_id, 
            self.user_message
        )
        context_data["retrieved_memories"] = retrieved_memories
```

### 3. `backend/app/core/conversation/prompts.py` ⚠️ **بازنویسی جزئی**

**تغییرات:**
- استفاده از `prompt_builder.py` برای ساخت prompt
- افزودن retrieved memories به prompt
- بهبود prompt engineering

**تغییرات:**
```python
def generate_response(...):
    # ... existing code ...
    
    # NEW: Use RAG prompt builder
    from app.core.conversation.rag.prompt_builder import build_rag_prompt
    
    messages = build_rag_prompt(
        system_prompt=system_prompt,
        retrieved_memories=context.get("retrieved_memories", []),
        conversation_history=conversation_history,
        user_message=user_message,
        health_data=context.get("health_data")
    )
```

### 4. `backend/app/core/conversation/brain.py` ⚠️ **بازنویسی جزئی**

**تغییرات:**
- اطمینان از ذخیره embeddings هنگام save_conversation
- استفاده از RAG در context building

---

## 🗄️ تغییرات دیتابیس

### Option 1: PostgreSQL + pgvector (پیشنهادی)

**مزایا:**
- یکپارچه با دیتابیس موجود
- Scalable
- Query performance خوب

**تغییرات:**
1. نصب extension: `CREATE EXTENSION vector;`
2. افزودن ستون به جدول `memories`:
```sql
ALTER TABLE memories ADD COLUMN embedding vector(1536);  -- OpenAI ada-002 dimension
CREATE INDEX ON memories USING ivfflat (embedding vector_cosine_ops);
```

### Option 2: جدول جداگانه برای embeddings

```sql
CREATE TABLE memory_embeddings (
    id SERIAL PRIMARY KEY,
    memory_id INTEGER REFERENCES memories(id),
    user_id INTEGER REFERENCES users(id),
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ON memory_embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON memory_embeddings (user_id);
```

---

## 📦 Dependencies جدید

### در `requirements.txt`:
```
# RAG Dependencies
openai>=1.0.0  # برای embeddings (اگر از OpenAI استفاده کنیم)
pgvector>=0.2.0  # برای PostgreSQL vector support
# یا
chromadb>=0.4.0  # اگر از ChromaDB استفاده کنیم
# یا
faiss-cpu>=1.7.4  # اگر از FAISS استفاده کنیم

# Optional: Reranking
sentence-transformers>=2.2.0  # برای reranking
```

---

## 🔧 پیاده‌سازی مرحله به مرحله

### Phase 1: Setup و Infrastructure
1. ✅ نصب dependencies
2. ✅ Setup vector database (pgvector یا ChromaDB)
3. ✅ ایجاد فایل‌های جدید (embeddings.py, vector_store.py, retriever.py)

### Phase 2: Embedding Generation
1. ✅ پیاده‌سازی `embeddings.py`
2. ✅ تست تولید embeddings
3. ✅ ذخیره embeddings در vector store

### Phase 3: Retrieval System
1. ✅ پیاده‌سازی `retriever.py`
2. ✅ تست semantic search
3. ✅ Integration با memory.py

### Phase 4: Prompt Engineering
1. ✅ پیاده‌سازی `prompt_builder.py`
2. ✅ بهبود system prompts با RAG context
3. ✅ تست prompt quality

### Phase 5: Integration
1. ✅ Integration با context.py
2. ✅ Integration با prompts.py
3. ✅ Integration با brain.py
4. ✅ تست end-to-end

### Phase 6: Optimization (Optional)
1. ✅ Reranking implementation
2. ✅ Caching برای embeddings
3. ✅ Performance optimization

---

## 💡 Prompt Engineering Best Practices

### 1. Structure Prompt به صورت واضح:
```
SYSTEM PROMPT:
- Identity and role
- Instructions
- Memory usage guidelines

RETRIEVED CONTEXT:
- Relevant memories from RAG
- Health data
- Lifestyle patterns

CONVERSATION HISTORY:
- Recent exchanges

USER MESSAGE:
- Current user input
```

### 2. استفاده از Few-Shot Examples:
```python
# در system prompt:
"""
EXAMPLES OF GOOD RESPONSES:
User: "I'm feeling tired"
Sedi: "I understand. Let's check your recent sleep patterns. How many hours did you sleep last night?"

User: "What should I eat?"
Sedi: "Based on your lifestyle, I'd suggest..."
"""
```

### 3. Context Prioritization:
- Recent messages: High priority
- Retrieved memories: Medium priority (if relevant)
- Health data: High priority (if available)
- Lifestyle patterns: Medium priority

---

## 🎯 مثال پیاده‌سازی

### مثال 1: ذخیره Embedding
```python
# در memory.py
def save_conversation_with_embedding(...):
    # Save conversation
    memory = self.save_conversation(...)
    
    # Generate embedding
    from app.core.conversation.rag.embeddings import generate_embedding
    text = f"{user_message} {sedi_response}"
    embedding = generate_embedding(text)
    
    # Store in vector database
    from app.core.conversation.rag.vector_store import store_memory_embedding
    store_memory_embedding(user_id, memory.id, embedding, text)
    
    return memory
```

### مثال 2: بازیابی با RAG
```python
# در context.py
def build(self):
    # ... existing code ...
    
    # RAG retrieval
    if self.user_message:
        from app.core.conversation.rag.retriever import retrieve_relevant_memories
        retrieved = retrieve_relevant_memories(
            user_id=self.user_id,
            query=self.user_message,
            memory_type="all",  # or "short", "medium", "long"
            limit=5
        )
        context_data["retrieved_memories"] = retrieved
```

### مثال 3: ساخت Prompt با RAG
```python
# در prompt_builder.py
def build_rag_prompt(...):
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Add retrieved context
    if retrieved_memories:
        context_text = "RELEVANT MEMORIES FROM PAST CONVERSATIONS:\n"
        for mem in retrieved_memories:
            context_text += f"- User: {mem['user_message']}\n"
            context_text += f"  Sedi: {mem['sedi_response']}\n"
        
        messages.append({
            "role": "system",
            "content": context_text
        })
    
    # Add conversation history
    for msg in conversation_history:
        messages.append({"role": "user", "content": msg["user"]})
        messages.append({"role": "assistant", "content": msg["sedi"]})
    
    # Add current message
    messages.append({"role": "user", "content": user_message})
    
    return messages
```

---

## 📊 مقایسه: قبل و بعد RAG

### قبل (فعلی):
```
User: "I mentioned I like running last week"
Sedi: "I see. What do you enjoy doing?"  ❌ (فراموش کرده)
```

### بعد (با RAG):
```
User: "I mentioned I like running last week"
Sedi: "Yes, I remember! You mentioned you enjoy running. How has your running been going this week?"  ✅ (یادآوری کرده)
```

---

## ⚠️ نکات مهم

1. **Performance:**
   - Embedding generation: ~100-200ms per request
   - Vector search: ~10-50ms (با index مناسب)
   - Total overhead: ~150-250ms

2. **Cost (اگر از OpenAI Embeddings استفاده کنیم):**
   - $0.0001 per 1K tokens
   - برای هر memory: ~$0.00001
   - برای 1000 memory: ~$0.01

3. **Storage:**
   - هر embedding: 1536 floats = ~6KB
   - برای 10,000 memory: ~60MB

4. **Backward Compatibility:**
   - باید متدهای موجود را حفظ کنیم
   - RAG باید optional باشد (می‌توان disable کرد)

---

## 🚀 شروع سریع

### Step 1: نصب Dependencies
```bash
pip install pgvector openai
```

### Step 2: Setup Database
```sql
CREATE EXTENSION vector;
ALTER TABLE memories ADD COLUMN embedding vector(1536);
```

### Step 3: ایجاد فایل‌ها
```
backend/app/core/conversation/rag/
  ├── __init__.py
  ├── embeddings.py
  ├── vector_store.py
  ├── retriever.py
  └── prompt_builder.py
```

### Step 4: پیاده‌سازی مرحله به مرحله
طبق Phase 1-6 بالا

---

## 📝 خلاصه

**فایل‌های جدید (5 فایل):**
1. `rag/__init__.py`
2. `rag/embeddings.py`
3. `rag/vector_store.py`
4. `rag/retriever.py`
5. `rag/prompt_builder.py` (یا `prompts.py` را بهبود دهیم)

**فایل‌های بازنویسی (4 فایل):**
1. `memory.py` - افزودن RAG support
2. `context.py` - استفاده از RAG retrieval
3. `prompts.py` - استفاده از prompt builder
4. `brain.py` - Integration با RAG

**تغییرات دیتابیس:**
- افزودن ستون `embedding` به `memories` یا جدول جداگانه

**Dependencies:**
- `pgvector` یا `chromadb` یا `faiss-cpu`
- `openai` (برای embeddings)

---

## ✅ نتیجه

با پیاده‌سازی RAG:
- Sedi می‌تواند از تمام تاریخچه گفتگو استفاده کند (نه فقط recent)
- پاسخ‌های مرتبط‌تر و شخصی‌تر می‌دهد
- اطلاعات قدیمی را فراموش نمی‌کند
- گفتگوی واقعی‌تر و زنده‌تر برقرار می‌کند

