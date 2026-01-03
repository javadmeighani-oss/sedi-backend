# app/core/conversation/question_database.py
"""
Question Database - Common questions in English, Persian, and Arabic

This module provides a comprehensive database of common questions that users might ask
during onboarding or general conversation. This helps distinguish questions from names.
"""

# ==================== COMMON QUESTIONS ====================

# English common questions
ENGLISH_QUESTIONS = {
    "about_sedi": [
        "who are you",
        "what are you",
        "what do you do",
        "what can you do",
        "tell me about yourself",
        "introduce yourself",
        "what is sedi",
        "who is sedi",
    ],
    "why_asking": [
        "why are you asking",
        "why do you need",
        "why ask",
        "why do you want",
        "why do you need my name",
        "why do you ask",
    ],
    "general": [
        "what is this",
        "what is going on",
        "what is happening",
        "how does this work",
        "how do i use this",
        "what should i do",
        "what do i need to do",
    ],
    "greeting_questions": [
        "how are you",
        "how is it going",
        "what's up",
        "how do you do",
    ],
}

# Persian common questions
PERSIAN_QUESTIONS = {
    "about_sedi": [
        "کی هستی",
        "کیستی",
        "چی هستی",
        "چی می‌کنی",
        "چی می‌تونی",
        "چی کار می‌کنی",
        "معرفی کن خودتو",
        "خودتو معرفی کن",
        "صدی چیه",
        "صدی کی هست",
        "صدی چی هست",
    ],
    "why_asking": [
        "چرا میپرسی",
        "چرا می‌پرسی",
        "چرا میپرس",
        "چرا می‌پرس",
        "چرا به اسم من نیاز داری",
        "چرا اسم من رو می‌خوای",
        "چرا اسم می‌خوای",
        "چرا نیاز داری",
        "چرا می‌خوای",
        "چرا می‌خوای اسم",
    ],
    "general": [
        "این چیه",
        "این چی هست",
        "چی شده",
        "چطور کار می‌کنه",
        "چطور استفاده کنم",
        "چی باید بکنم",
        "باید چیکار کنم",
        "چی کار کنم",
    ],
    "greeting_questions": [
        "چطوری",
        "چطوره",
        "خوبی",
        "حالت چطوره",
    ],
}

# Arabic common questions
ARABIC_QUESTIONS = {
    "about_sedi": [
        "من أنت",
        "ما أنت",
        "ماذا تفعل",
        "ماذا يمكنك",
        "عرف نفسك",
        "قدم نفسك",
        "ما هو صدي",
        "من هو صدي",
    ],
    "why_asking": [
        "لماذا تسأل",
        "لماذا تحتاج",
        "لماذا تطلب",
        "لماذا تحتاج اسمي",
        "لماذا تريد اسمي",
    ],
    "general": [
        "ما هذا",
        "ماذا يحدث",
        "كيف يعمل",
        "كيف أستخدم",
        "ماذا يجب أن أفعل",
    ],
    "greeting_questions": [
        "كيف حالك",
        "كيف أنت",
    ],
}

# Combine all questions
ALL_QUESTIONS = {
    "en": [q for category in ENGLISH_QUESTIONS.values() for q in category],
    "fa": [q for category in PERSIAN_QUESTIONS.values() for q in category],
    "ar": [q for category in ARABIC_QUESTIONS.values() for q in category],
}

# ==================== HELPER FUNCTIONS ====================

def is_common_question(text: str, language: str = "auto") -> bool:
    """
    Check if text is a common question from the database.
    
    Args:
        text: User input text
        language: Language code ("en", "fa", "ar", "auto")
    
    Returns:
        bool: True if text is a common question
    """
    text_clean = text.strip().lower()
    text_original = text.strip()  # Keep original for Persian/Arabic
    
    # Auto-detect language if requested
    if language == "auto":
        from app.core.conversation.name_database import detect_language
        language = detect_language(text)
    
    # Check against question database based on language
    question_list = ALL_QUESTIONS.get(language, ALL_QUESTIONS["en"])
    
    # Check exact match (case-insensitive for English, exact for Persian/Arabic)
    if text_clean in question_list or text_original in question_list:
        return True
    
    # CRITICAL: Check if any question from database is contained in the text
    # This handles cases where user might add extra words or punctuation
    for question in question_list:
        # Check if question is in text (both clean and original)
        if question in text_clean or question in text_original:
            return True
        # Also check reverse (text in question) for partial matches
        if text_clean in question or text_original in question:
            return True
    
    # CRITICAL: Also check in all languages as fallback (especially Persian)
    # This ensures we catch questions even if language detection is wrong
    for lang, questions in ALL_QUESTIONS.items():
        if lang != language:
            for question in questions:
                if question in text_clean or question in text_original:
                    return True
                # Also check reverse for partial matches
                if text_clean in question or text_original in question:
                    return True
    
    return False


def get_question_category(text: str, language: str = "auto") -> str:
    """
    Get the category of a question if it's a common question.
    
    Args:
        text: User input text
        language: Language code ("en", "fa", "ar", "auto")
    
    Returns:
        str: Question category or None
    """
    text_clean = text.strip().lower()
    text_original = text.strip()
    
    # Auto-detect language if requested
    if language == "auto":
        from app.core.conversation.name_database import detect_language
        language = detect_language(text)
    
    # Check each category
    if language == "en":
        for category, questions in ENGLISH_QUESTIONS.items():
            for question in questions:
                if question in text_clean or question in text_original:
                    return category
    elif language == "fa":
        for category, questions in PERSIAN_QUESTIONS.items():
            for question in questions:
                if question in text_clean or question in text_original:
                    return category
    elif language == "ar":
        for category, questions in ARABIC_QUESTIONS.items():
            for question in questions:
                if question in text_clean or question in text_original:
                    return category
    
    return None

