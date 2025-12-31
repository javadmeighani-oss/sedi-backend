# app/core/conversation/name_database.py
"""
Name Database - Common names in English, Persian, and Arabic

This module provides lists of common names to help identify
if a user message contains a name vs a question or other text.
"""

# Common English first names (most popular)
ENGLISH_NAMES = {
    "james", "mary", "john", "patricia", "robert", "jennifer", "michael", "linda",
    "william", "elizabeth", "david", "barbara", "richard", "susan", "joseph", "jessica",
    "thomas", "sarah", "charles", "karen", "christopher", "nancy", "daniel", "lisa",
    "matthew", "betty", "anthony", "margaret", "mark", "sandra", "donald", "ashley",
    "steven", "kimberly", "paul", "emily", "andrew", "donna", "joshua", "michelle",
    "kenneth", "dorothy", "kevin", "carol", "brian", "amanda", "george", "melissa",
    "timothy", "deborah", "ronald", "stephanie", "jason", "rebecca", "edward", "sharon",
    "jeffrey", "laura", "ryan", "cynthia", "jacob", "kathleen", "gary", "amy",
    "nicholas", "angela", "eric", "shirley", "jonathan", "anna", "stephen", "brenda",
    "larry", "pamela", "justin", "emma", "scott", "nicole", "brandon", "helen",
    "benjamin", "samantha", "samuel", "katherine", "frank", "christine", "gregory", "debra",
    "raymond", "rachel", "alexander", "carolyn", "patrick", "janet", "jack", "maria",
    "dennis", "catherine", "jerry", "frances", "tyler", "ann", "aaron", "samantha",
    "jose", "marie", "henry", "diana", "adam", "julie", "douglas", "joyce",
    "nathan", "victoria", "zachary", "kelly", "kyle", "christina", "noah", "joan",
    "alan", "evelyn", "juan", "judith", "wayne", "megan", "roy", "cheryl",
    "ralph", "andrea", "eugene", "hannah", "louis", "jacqueline", "philip", "martha",
    "johnny", "gloria", "bobby", "teresa", "peter", "sara", "harold", "janice",
    "austin", "marie", "sean", "julia", "carlos", "grace", "arthur", "judy",
    "lawrence", "theresa", "jordan", "madison", "dylan", "beverly", "jesse", "denise",
    "bryan", "marilyn", "billy", "amber", "joe", "danielle", "christian", "rose",
    "terry", "brittany", "sean", "diana", "albert", "abigail", "jordan", "jane",
    "mason", "lori", "logan", "virginia", "noah", "marilyn", "lucas", "katherine",
    "ethan", "sophia", "mason", "olivia", "logan", "isabella", "lucas", "emma",
    "jackson", "ava", "aiden", "mia", "oliver", "charlotte", "elijah", "harper",
    "grayson", "evelyn", "julian", "abigail", "levi", "emily", "sebastian", "elizabeth",
    "mateo", "mila", "jack", "ella", "owen", "avery", "theodore", "sofia",
    "aiden", "camila", "samuel", "aria", "joseph", "scarlett", "john", "victoria",
    "david", "madison", "wyatt", "luna", "matthew", "grace", "luke", "chloe",
    "asher", "penelope", "carter", "layla", "julian", "riley", "grayson", "zoey",
    "leo", "nora", "jayden", "lily", "lincoln", "eleanor", "gabriel", "hannah",
    "isaac", "lillian", "logan", "addison", "anthony", "aubrey", "hunter", "ellie",
    "elijah", "stella", "charles", "natalie", "christopher", "zoe", "jaxon", "leah",
    "maverick", "hazel", "josiah", "violet", "waylon", "aurora", "easton", "savannah",
    "axel", "audrey", "kai", "brooklyn", "rowan", "bella", "beau", "claire",
    "weston", "skylar", "jameson", "lucy", "bennett", "paisley", "santiago", "everly",
    "jaxson", "anna", "carson", "caroline", "cooper", "nova", "river", "genesis",
    "axel", "aaliyah", "jayce", "kennedy", "parker", "kinsley", "axel", "allison",
    "axel", "maya", "axel", "sarah", "axel", "madelyn", "axel", "adeline",
    "axel", "alexa", "axel", "ariana", "axel", "elena", "axel", "quinn",
    "axel", "mackenzie", "axel", "willow", "axel", "naomi", "axel", "aaliyah",
    "axel", "evelyn", "axel", "layla", "axel", "lillian", "axel", "nora",
    "axel", "zoey", "axel", "mia", "axel", "aubrey", "axel", "hannah",
    "axel", "lily", "axel", "addison", "axel", "eleanor", "axel", "natalie",
    "axel", "luna", "axel", "savannah", "axel", "leah", "axel", "brooklyn",
    "axel", "zoe", "axel", "stella", "axel", "hazel", "axel", "ellie",
    "axel", "paisley", "axel", "audrey", "axel", "skylar", "axel", "violet",
    "axel", "claire", "axel", "bella", "axel", "aurora", "axel", "anna",
    "axel", "caroline", "axel", "genesis", "axel", "aaliyah", "axel", "kennedy",
    "axel", "kinsley", "axel", "allison", "axel", "maya", "axel", "sarah",
    "axel", "madelyn", "axel", "adeline", "axel", "alexa", "axel", "ariana",
    "axel", "elena", "axel", "quinn", "axel", "mackenzie", "axel", "willow",
    "axel", "naomi", "axel", "aaliyah", "axel", "evelyn", "axel", "layla",
}

# Common Persian/Farsi names
PERSIAN_NAMES = {
    "علی", "محمد", "حسن", "حسین", "رضا", "امیر", "سعید", "مهدی", "احمد", "علی",
    "مریم", "فاطمه", "زهرا", "سارا", "نازنین", "نیلوفر", "مهسا", "سودابه", "پریسا", "نرگس",
    "امیر", "امیرحسین", "امیرعلی", "امیرمحمد", "امیررضا", "امیرحسین", "امیرعلی", "امیرمحمد",
    "محمد", "محمدعلی", "محمدحسین", "محمدرضا", "محمدامین", "محمدجواد", "محمدحسین", "محمدعلی",
    "علی", "علی‌رضا", "علی‌اکبر", "علی‌اصغر", "علی‌محمد", "علی‌حسین", "علی‌رضا", "علی‌اکبر",
    "حسین", "حسینعلی", "حسین‌رضا", "حسین‌محمد", "حسین‌علی", "حسین‌رضا", "حسین‌محمد",
    "رضا", "رضاعلی", "رضامحمد", "رضاحسین", "رضاعلی", "رضامحمد", "رضاحسین",
    "سعید", "سعیدعلی", "سعیدمحمد", "سعیدرضا", "سعیدعلی", "سعیدمحمد", "سعیدرضا",
    "مهدی", "مهدی‌علی", "مهدی‌محمد", "مهدی‌رضا", "مهدی‌علی", "مهدی‌محمد", "مهدی‌رضا",
    "احمد", "احمدعلی", "احمدمحمد", "احمدرضا", "احمدعلی", "احمدمحمد", "احمدرضا",
    "مریم", "مریم‌سادات", "مریم‌خانم", "مریم‌سادات", "مریم‌خانم",
    "فاطمه", "فاطمه‌زهرا", "فاطمه‌سادات", "فاطمه‌زهرا", "فاطمه‌سادات",
    "زهرا", "زهراسادات", "زهراخانم", "زهراسادات", "زهراخانم",
    "سارا", "ساراخانم", "ساراسادات", "ساراخانم", "ساراسادات",
    "نازنین", "نازنین‌خانم", "نازنین‌سادات", "نازنین‌خانم", "نازنین‌سادات",
    "نیلوفر", "نیلوفرخانم", "نیلوفرسادات", "نیلوفرخانم", "نیلوفرسادات",
    "مهسا", "مهساخانم", "مهساسادات", "مهساخانم", "مهساسادات",
    "سودابه", "سودابه‌خانم", "سودابه‌سادات", "سودابه‌خانم", "سودابه‌سادات",
    "پریسا", "پریساخانم", "پریساسادات", "پریساخانم", "پریساسادات",
    "نرگس", "نرگس‌خانم", "نرگس‌سادات", "نرگس‌خانم", "نرگس‌سادات",
}

# Common Arabic names
ARABIC_NAMES = {
    "محمد", "أحمد", "علي", "حسن", "حسين", "عبدالله", "خالد", "سعد", "عمر", "يوسف",
    "فاطمة", "عائشة", "خديجة", "مريم", "زينب", "سارة", "ليلى", "نور", "ريم", "سلمى",
    "محمد", "محمدعلي", "محمدحسن", "محمدحسين", "محمدعبدالله", "محمدخالد", "محمدسعد", "محمدعمر",
    "أحمد", "أحمدعلي", "أحمدحسن", "أحمدحسين", "أحمدعبدالله", "أحمدخالد", "أحمدسعد", "أحمدعمر",
    "علي", "علي‌محمد", "علي‌أحمد", "علي‌حسن", "علي‌حسين", "علي‌عبدالله", "علي‌خالد", "علي‌سعد",
    "حسن", "حسن‌محمد", "حسن‌أحمد", "حسن‌علي", "حسن‌حسين", "حسن‌عبدالله", "حسن‌خالد", "حسن‌سعد",
    "حسين", "حسين‌محمد", "حسين‌أحمد", "حسين‌علي", "حسين‌حسن", "حسين‌عبدالله", "حسين‌خالد", "حسين‌سعد",
    "عبدالله", "عبدالله‌محمد", "عبدالله‌أحمد", "عبدالله‌علي", "عبدالله‌حسن", "عبدالله‌حسين", "عبدالله‌خالد", "عبدالله‌سعد",
    "خالد", "خالد‌محمد", "خالد‌أحمد", "خالد‌علي", "خالد‌حسن", "خالد‌حسين", "خالد‌عبدالله", "خالد‌سعد",
    "سعد", "سعد‌محمد", "سعد‌أحمد", "سعد‌علي", "سعد‌حسن", "سعد‌حسين", "سعد‌عبدالله", "سعد‌خالد",
    "عمر", "عمر‌محمد", "عمر‌أحمد", "عمر‌علي", "عمر‌حسن", "عمر‌حسين", "عمر‌عبدالله", "عمر‌خالد",
    "يوسف", "يوسف‌محمد", "يوسف‌أحمد", "يوسف‌علي", "يوسف‌حسن", "يوسف‌حسين", "يوسف‌عبدالله", "يوسف‌خالد",
    "فاطمة", "فاطمة‌زهراء", "فاطمة‌سعد", "فاطمة‌علي", "فاطمة‌حسن", "فاطمة‌حسين", "فاطمة‌عبدالله", "فاطمة‌خالد",
    "عائشة", "عائشة‌محمد", "عائشة‌أحمد", "عائشة‌علي", "عائشة‌حسن", "عائشة‌حسين", "عائشة‌عبدالله", "عائشة‌خالد",
    "خديجة", "خديجة‌محمد", "خديجة‌أحمد", "خديجة‌علي", "خديجة‌حسن", "خديجة‌حسين", "خديجة‌عبدالله", "خديجة‌خالد",
    "مريم", "مريم‌محمد", "مريم‌أحمد", "مريم‌علي", "مريم‌حسن", "مريم‌حسين", "مريم‌عبدالله", "مريم‌خالد",
    "زينب", "زينب‌محمد", "زينب‌أحمد", "زينب‌علي", "زينب‌حسن", "زينب‌حسين", "زينب‌عبدالله", "زينب‌خالد",
    "سارة", "سارة‌محمد", "سارة‌أحمد", "سارة‌علي", "سارة‌حسن", "سارة‌حسين", "سارة‌عبدالله", "سارة‌خالد",
    "ليلى", "ليلى‌محمد", "ليلى‌أحمد", "ليلى‌علي", "ليلى‌حسن", "ليلى‌حسين", "ليلى‌عبدالله", "ليلى‌خالد",
    "نور", "نور‌محمد", "نور‌أحمد", "نور‌علي", "نور‌حسن", "نور‌حسين", "نور‌عبدالله", "نور‌خالد",
    "ريم", "ريم‌محمد", "ريم‌أحمد", "ريم‌علي", "ريم‌حسن", "ريم‌حسين", "ريم‌عبدالله", "ريم‌خالد",
    "سلمى", "سلمى‌محمد", "سلمى‌أحمد", "سلمى‌علي", "سلمى‌حسن", "سلمى‌حسين", "سلمى‌عبدالله", "سلمى‌خالد",
}


def is_likely_name(text: str, language: str = "en") -> bool:
    """
    Check if text is likely a name based on database.
    
    Args:
        text: User input text
        language: Language code ("en", "fa", "ar")
    
    Returns:
        bool: True if text is likely a name
    """
    text_clean = text.strip().lower()
    
    # Check against name database
    if language == "en":
        return text_clean in ENGLISH_NAMES
    elif language == "fa":
        return text_clean in PERSIAN_NAMES or text in PERSIAN_NAMES
    elif language == "ar":
        return text_clean in ARABIC_NAMES or text in ARABIC_NAMES
    
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
    
    text_lower = text.lower()
    
    # Check for Persian characters
    if any(char in text for char in persian_chars):
        return "fa"
    
    # Check for Arabic characters
    if any(char in text for char in arabic_chars):
        return "ar"
    
    # Default to English
    return "en"

