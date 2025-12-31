# app/core/conversation/name_database.py
"""
Name Database - Comprehensive database of common names in English, Persian, and Arabic

This module provides extensive lists of common names to help identify
if a user message contains a name vs a question or other text.
"""

# ==================== ENGLISH NAMES ====================

# Common English Male Names
ENGLISH_MALE_NAMES = {
    # Classic/Traditional
    "james", "john", "robert", "michael", "william", "david", "richard", "joseph",
    "thomas", "charles", "christopher", "daniel", "matthew", "anthony", "mark",
    "donald", "steven", "paul", "andrew", "joshua", "kenneth", "kevin", "brian",
    "george", "timothy", "ronald", "jason", "edward", "jeffrey", "ryan", "jacob",
    "gary", "nicholas", "eric", "jonathan", "stephen", "larry", "justin", "scott",
    "brandon", "benjamin", "samuel", "frank", "gregory", "raymond", "alexander",
    "patrick", "jack", "dennis", "jerry", "tyler", "aaron", "jose", "henry",
    "adam", "douglas", "nathan", "zachary", "kyle", "noah", "alan", "juan",
    "wayne", "roy", "ralph", "eugene", "louis", "philip", "johnny", "bobby",
    "peter", "harold", "austin", "carlos", "arthur", "lawrence", "jordan",
    "dylan", "bryan", "billy", "joe", "christian", "terry", "sean", "albert",
    "mason", "logan", "lucas", "ethan", "jackson", "aiden", "oliver", "elijah",
    "grayson", "julian", "levi", "sebastian", "mateo", "jack", "owen", "theodore",
    "samuel", "wyatt", "luke", "asher", "carter", "julian", "leo", "jayden",
    "lincoln", "gabriel", "isaac", "logan", "anthony", "hunter", "elijah",
    "charles", "christopher", "jaxon", "maverick", "josiah", "waylon", "easton",
    "axel", "kai", "rowan", "beau", "weston", "jameson", "bennett", "santiago",
    "jaxson", "carson", "cooper", "river", "axel", "jayce", "parker", "axel",
    # Modern/Popular
    "liam", "noah", "oliver", "william", "elijah", "james", "benjamin", "lucas",
    "mason", "ethan", "alexander", "henry", "jacob", "michael", "daniel", "logan",
    "jackson", "levi", "sebastian", "mateo", "jack", "owen", "theodore", "aiden",
    "samuel", "joseph", "john", "david", "wyatt", "matthew", "luke", "asher",
    "carter", "julian", "grayson", "leo", "jayden", "lincoln", "gabriel", "isaac",
    "anthony", "hunter", "elijah", "charles", "christopher", "jaxon", "maverick",
    "josiah", "waylon", "easton", "axel", "kai", "rowan", "beau", "weston",
    "jameson", "bennett", "santiago", "jaxson", "carson", "cooper", "river",
    "jayce", "parker", "axel", "axel", "axel", "axel", "axel", "axel",
}

# Common English Female Names
ENGLISH_FEMALE_NAMES = {
    # Classic/Traditional
    "mary", "patricia", "jennifer", "linda", "elizabeth", "barbara", "susan",
    "jessica", "sarah", "karen", "nancy", "lisa", "betty", "margaret", "sandra",
    "ashley", "kimberly", "emily", "donna", "michelle", "dorothy", "carol",
    "amanda", "melissa", "deborah", "stephanie", "rebecca", "sharon", "laura",
    "cynthia", "kathleen", "amy", "angela", "shirley", "anna", "brenda", "pamela",
    "nicole", "emma", "helen", "samantha", "katherine", "christine", "debra",
    "rachel", "carolyn", "janet", "maria", "catherine", "frances", "ann", "diana",
    "julie", "joyce", "victoria", "kelly", "christina", "joan", "evelyn", "judith",
    "megan", "cheryl", "andrea", "hannah", "jacqueline", "martha", "gloria",
    "teresa", "sara", "janice", "marie", "julia", "grace", "judy", "theresa",
    "madison", "beverly", "denise", "marilyn", "amber", "danielle", "rose",
    "brittany", "diana", "abigail", "jane", "virginia", "lori", "katherine",
    "sophia", "olivia", "isabella", "emma", "ava", "mia", "charlotte", "harper",
    "evelyn", "abigail", "emily", "elizabeth", "mila", "ella", "avery", "sofia",
    "camila", "aria", "scarlett", "victoria", "madison", "luna", "grace", "chloe",
    "penelope", "layla", "riley", "zoey", "nora", "lily", "eleanor", "hannah",
    "lillian", "addison", "aubrey", "ellie", "stella", "natalie", "zoe", "leah",
    "hazel", "violet", "aurora", "savannah", "audrey", "brooklyn", "bella",
    "claire", "skylar", "lucy", "paisley", "everly", "anna", "caroline", "nova",
    "genesis", "aaliyah", "kennedy", "kinsley", "allison", "maya", "sarah",
    "madelyn", "adeline", "alexa", "ariana", "elena", "quinn", "mackenzie",
    "willow", "naomi", "aaliyah", "evelyn", "layla", "lillian", "nora", "zoey",
    "mia", "aubrey", "hannah", "lily", "addison", "eleanor", "natalie", "luna",
    "savannah", "leah", "brooklyn", "zoe", "stella", "hazel", "ellie", "paisley",
    "audrey", "skylar", "violet", "claire", "bella", "aurora", "anna", "caroline",
    "genesis", "aaliyah", "kennedy", "kinsley", "allison", "maya", "sarah",
    "madelyn", "adeline", "alexa", "ariana", "elena", "quinn", "mackenzie",
    "willow", "naomi",
}

# Combined English Names
ENGLISH_NAMES = ENGLISH_MALE_NAMES | ENGLISH_FEMALE_NAMES

# ==================== PERSIAN/FARSI NAMES ====================

# Common Persian Male Names
PERSIAN_MALE_NAMES = {
    # Traditional/Religious
    "علی", "محمد", "حسن", "حسین", "رضا", "امیر", "سعید", "مهدی", "احمد",
    "علی‌رضا", "علی‌اکبر", "علی‌اصغر", "علی‌محمد", "علی‌حسین",
    "محمدعلی", "محمدحسین", "محمدرضا", "محمدامین", "محمدجواد", "محمدحسین",
    "حسینعلی", "حسین‌رضا", "حسین‌محمد",
    "رضاعلی", "رضامحمد", "رضاحسین",
    "سعیدعلی", "سعیدمحمد", "سعیدرضا",
    "مهدی‌علی", "مهدی‌محمد", "مهدی‌رضا",
    "احمدعلی", "احمدمحمد", "احمدرضا",
    # Modern/Popular
    "امیرحسین", "امیرعلی", "امیرمحمد", "امیررضا",
    "پارسا", "آرین", "آریا", "کیان", "کامیار", "سینا", "نیما", "بنیامین",
    "دانیال", "یاسین", "ایلیا", "رایان", "آرمان", "آرمین", "آراد", "آرین",
    "آرمان", "آرین", "آراد", "آرین", "آرمان", "آرین", "آراد", "آرین",
    "امیر", "امیرحسین", "امیرعلی", "امیرمحمد", "امیررضا",
    "پویا", "پیمان", "پژمان", "پدرام", "پوریا", "پیمان", "پژمان", "پدرام",
    "تیمور", "تیمور", "تیمور", "تیمور",
    "حسام", "حسام‌الدین", "حسام", "حسام‌الدین",
    "دانیال", "دانیال", "دانیال", "دانیال",
    "رامین", "رامین", "رامین", "رامین",
    "سامان", "سامان", "سامان", "سامان",
    "شایان", "شایان", "شایان", "شایان",
    "عرفان", "عرفان", "عرفان", "عرفان",
    "فرهاد", "فرهاد", "فرهاد", "فرهاد",
    "کامران", "کامران", "کامران", "کامران",
    "کیوان", "کیوان", "کیوان", "کیوان",
    "مازیار", "مازیار", "مازیار", "مازیار",
    "نیما", "نیما", "نیما", "نیما",
    "یاسین", "یاسین", "یاسین", "یاسین",
}

# Common Persian Female Names
PERSIAN_FEMALE_NAMES = {
    # Traditional/Religious
    "مریم", "فاطمه", "زهرا", "سارا", "نازنین", "نیلوفر", "مهسا", "سودابه",
    "پریسا", "نرگس", "فاطمه‌زهرا", "فاطمه‌سادات", "زهراسادات", "زهراخانم",
    "ساراخانم", "ساراسادات", "نازنین‌خانم", "نازنین‌سادات",
    "نیلوفرخانم", "نیلوفرسادات", "مهساخانم", "مهساسادات",
    "سودابه‌خانم", "سودابه‌سادات", "پریساخانم", "پریساسادات",
    "نرگس‌خانم", "نرگس‌سادات", "مریم‌سادات", "مریم‌خانم",
    # Modern/Popular
    "آرین", "آرینا", "آرینا", "آرینا",
    "آتوسا", "آتوسا", "آتوسا", "آتوسا",
    "آیدا", "آیدا", "آیدا", "آیدا",
    "آناهیتا", "آناهیتا", "آناهیتا", "آناهیتا",
    "باران", "باران", "باران", "باران",
    "بهار", "بهار", "بهار", "بهار",
    "پریا", "پریا", "پریا", "پریا",
    "ترانه", "ترانه", "ترانه", "ترانه",
    "دلارام", "دلارام", "دلارام", "دلارام",
    "رؤیا", "رؤیا", "رؤیا", "رؤیا",
    "سارا", "سارا", "سارا", "سارا",
    "سپیده", "سپیده", "سپیده", "سپیده",
    "شیدا", "شیدا", "شیدا", "شیدا",
    "غزل", "غزل", "غزل", "غزل",
    "فرزانه", "فرزانه", "فرزانه", "فرزانه",
    "کیمیا", "کیمیا", "کیمیا", "کیمیا",
    "لیلا", "لیلا", "لیلا", "لیلا",
    "مبینا", "مبینا", "مبینا", "مبینا",
    "مهسا", "مهسا", "مهسا", "مهسا",
    "نیلوفر", "نیلوفر", "نیلوفر", "نیلوفر",
    "یاسمن", "یاسمن", "یاسمن", "یاسمن",
}

# Combined Persian Names
PERSIAN_NAMES = PERSIAN_MALE_NAMES | PERSIAN_FEMALE_NAMES

# ==================== ARABIC NAMES ====================

# Common Arabic Male Names
ARABIC_MALE_NAMES = {
    # Traditional/Religious
    "محمد", "أحمد", "علي", "حسن", "حسين", "عبدالله", "خالد", "سعد", "عمر", "يوسف",
    "محمدعلي", "محمدحسن", "محمدحسين", "محمدعبدالله", "محمدخالد", "محمدسعد", "محمدعمر",
    "أحمدعلي", "أحمدحسن", "أحمدحسين", "أحمدعبدالله", "أحمدخالد", "أحمدسعد", "أحمدعمر",
    "علي‌محمد", "علي‌أحمد", "علي‌حسن", "علي‌حسين", "علي‌عبدالله", "علي‌خالد", "علي‌سعد",
    "حسن‌محمد", "حسن‌أحمد", "حسن‌علي", "حسن‌حسين", "حسن‌عبدالله", "حسن‌خالد", "حسن‌سعد",
    "حسين‌محمد", "حسين‌أحمد", "حسين‌علي", "حسين‌حسن", "حسين‌عبدالله", "حسين‌خالد", "حسين‌سعد",
    "عبدالله‌محمد", "عبدالله‌أحمد", "عبدالله‌علي", "عبدالله‌حسن", "عبدالله‌حسين", "عبدالله‌خالد", "عبدالله‌سعد",
    "خالد‌محمد", "خالد‌أحمد", "خالد‌علي", "خالد‌حسن", "خالد‌حسين", "خالد‌عبدالله", "خالد‌سعد",
    "سعد‌محمد", "سعد‌أحمد", "سعد‌علي", "سعد‌حسن", "سعد‌حسين", "سعد‌عبدالله", "سعد‌خالد",
    "عمر‌محمد", "عمر‌أحمد", "عمر‌علي", "عمر‌حسن", "عمر‌حسين", "عمر‌عبدالله", "عمر‌خالد",
    "يوسف‌محمد", "يوسف‌أحمد", "يوسف‌علي", "يوسف‌حسن", "يوسف‌حسين", "يوسف‌عبدالله", "يوسف‌خالد",
    # Modern/Popular
    "عبدالرحمن", "عبدالرحيم", "عبدالعزيز", "عبدالملك", "عبدالوهاب",
    "محمود", "مصطفى", "موسى", "إبراهيم", "إسماعيل", "إسحاق", "يعقوب",
    "طارق", "طارق", "طارق", "طارق",
    "زياد", "زياد", "زياد", "زياد",
    "فادي", "فادي", "فادي", "فادي",
    "مروان", "مروان", "مروان", "مروان",
    "نادر", "نادر", "نادر", "نادر",
    "وائل", "وائل", "وائل", "وائل",
    "ياسر", "ياسر", "ياسر", "ياسر",
}

# Common Arabic Female Names
ARABIC_FEMALE_NAMES = {
    # Traditional/Religious
    "فاطمة", "عائشة", "خديجة", "مريم", "زينب", "سارة", "ليلى", "نور", "ريم", "سلمى",
    "فاطمة‌زهراء", "فاطمة‌سعد", "فاطمة‌علي", "فاطمة‌حسن", "فاطمة‌حسين", "فاطمة‌عبدالله", "فاطمة‌خالد",
    "عائشة‌محمد", "عائشة‌أحمد", "عائشة‌علي", "عائشة‌حسن", "عائشة‌حسين", "عائشة‌عبدالله", "عائشة‌خالد",
    "خديجة‌محمد", "خديجة‌أحمد", "خديجة‌علي", "خديجة‌حسن", "خديجة‌حسين", "خديجة‌عبدالله", "خديجة‌خالد",
    "مريم‌محمد", "مريم‌أحمد", "مريم‌علي", "مريم‌حسن", "مريم‌حسين", "مريم‌عبدالله", "مريم‌خالد",
    "زينب‌محمد", "زينب‌أحمد", "زينب‌علي", "زينب‌حسن", "زينب‌حسين", "زينب‌عبدالله", "زينب‌خالد",
    "سارة‌محمد", "سارة‌أحمد", "سارة‌علي", "سارة‌حسن", "سارة‌حسين", "سارة‌عبدالله", "سارة‌خالد",
    "ليلى‌محمد", "ليلى‌أحمد", "ليلى‌علي", "ليلى‌حسن", "ليلى‌حسين", "ليلى‌عبدالله", "ليلى‌خالد",
    "نور‌محمد", "نور‌أحمد", "نور‌علي", "نور‌حسن", "نور‌حسين", "نور‌عبدالله", "نور‌خالد",
    "ريم‌محمد", "ريم‌أحمد", "ريم‌علي", "ريم‌حسن", "ريم‌حسين", "ريم‌عبدالله", "ريم‌خالد",
    "سلمى‌محمد", "سلمى‌أحمد", "سلمى‌علي", "سلمى‌حسن", "سلمى‌حسين", "سلمى‌عبدالله", "سلمى‌خالد",
    # Modern/Popular
    "آمنة", "آمنة", "آمنة", "آمنة",
    "إيمان", "إيمان", "إيمان", "إيمان",
    "بسمة", "بسمة", "بسمة", "بسمة",
    "جمانة", "جمانة", "جمانة", "جمانة",
    "حبيبة", "حبيبة", "حبيبة", "حبيبة",
    "دعاء", "دعاء", "دعاء", "دعاء",
    "رنا", "رنا", "رنا", "رنا",
    "سجى", "سجى", "سجى", "سجى",
    "شيماء", "شيماء", "شيماء", "شيماء",
    "ضحى", "ضحى", "ضحى", "ضحى",
    "عائشة", "عائشة", "عائشة", "عائشة",
    "فاطمة", "فاطمة", "فاطمة", "فاطمة",
    "كرمة", "كرمة", "كرمة", "كرمة",
    "ليلى", "ليلى", "ليلى", "ليلى",
    "مريم", "مريم", "مريم", "مريم",
    "نور", "نور", "نور", "نور",
    "هبة", "هبة", "هبة", "هبة",
    "ياسمين", "ياسمين", "ياسمين", "ياسمين",
}

# Combined Arabic Names
ARABIC_NAMES = ARABIC_MALE_NAMES | ARABIC_FEMALE_NAMES


def is_likely_name(text: str, language: str = "en") -> bool:
    """
    Check if text is likely a name based on comprehensive database.
    
    Args:
        text: User input text
        language: Language code ("en", "fa", "ar")
    
    Returns:
        bool: True if text is likely a name
    """
    text_clean = text.strip().lower()
    text_original = text.strip()  # Keep original for Persian/Arabic
    
    # Check against name database
    if language == "en":
        return text_clean in ENGLISH_NAMES
    elif language == "fa":
        # Check both lowercase and original (Persian doesn't have case)
        return text_clean in PERSIAN_NAMES or text_original in PERSIAN_NAMES
    elif language == "ar":
        # Check both lowercase and original (Arabic doesn't have case)
        return text_clean in ARABIC_NAMES or text_original in ARABIC_NAMES
    
    # Fallback: check if it's a short word without digits or special chars
    if 2 <= len(text_clean) <= 30:
        if not any(char.isdigit() for char in text_clean):
            if not any(char in text_clean for char in ["?", "؟", "!", "!", ".", "،", ","]):
                return True
    
    return False


def detect_language(text: str) -> str:
    """
    Detect language of user message.
    
    Args:
        text: User message
    
    Returns:
        str: Language code ("en", "fa", "ar")
    """
    # Persian/Farsi characters
    persian_chars = "ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی"
    # Arabic characters (some overlap with Persian)
    arabic_chars = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"
    
    # Check for Persian characters
    if any(char in text for char in persian_chars):
        return "fa"
    
    # Check for Arabic characters
    if any(char in text for char in arabic_chars):
        return "ar"
    
    # Default to English
    return "en"
