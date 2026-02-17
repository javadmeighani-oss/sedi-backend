# app/core/conversation/name_database.py
"""
Name Database - Comprehensive database of common names categorized by language and script

This module provides extensive lists of common names organized into:
1. English names (pure English names)
2. Persian names (in Persian/Farsi script)
3. Arabic names (in Arabic script)
4. Persian names transliterated (Persian names written in English letters)
5. Arabic names transliterated (Arabic names written in English letters)
6. Mixed names (English names with Persian/Arabic text)

This helps identify if a user message contains a name vs a question or other text.
"""

# ==================== CATEGORY 1: ENGLISH NAMES (Pure English) ====================

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
    "grayson", "julian", "levi", "sebastian", "mateo", "owen", "theodore",
    "wyatt", "luke", "asher", "carter", "leo", "jayden",
    "lincoln", "gabriel", "isaac", "hunter",
    "jaxon", "maverick", "josiah", "waylon", "easton",
    "axel", "kai", "rowan", "beau", "weston",
    "jameson", "bennett", "santiago", "jaxson", "carson", "cooper", "river",
    "jayce", "parker",
    # Additional Common Names
    "alex", "alexander", "anthony", "austin", "blake", "caleb", "cameron",
    "connor", "cristian", "damian", "diego", "dominic", "elias", "elliot",
    "emmanuel", "evan", "ezra", "finn", "gianni", "graham", "grant", "hayden",
    "holden", "ian", "isaiah", "ivan", "jaden", "jake", "james", "jaxon",
    "jeremiah", "jesse", "jesus", "joel", "jonah", "jordan", "jose", "joshua",
    "julian", "justin", "kaden", "kai", "kaleb", "kameron", "kayden", "keegan",
    "kenneth", "kevin", "king", "knox", "kobe", "kyle", "landon", "leo", "liam",
    "lincoln", "logan", "luca", "lucas", "luis", "marcus", "mason", "mateo",
    "max", "maxwell", "micah", "miles", "myles", "nathan", "nathaniel", "nicholas",
    "noah", "nolan", "oliver", "oscar", "owen", "parker", "patrick", "paul",
    "peter", "preston", "quinn", "riley", "robert", "roman", "ryan", "samuel",
    "santiago", "sebastian", "silas", "simon", "thomas", "tristan", "tyler",
    "victor", "vincent", "wesley", "william", "wyatt", "xavier", "zachary", "zane",
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
    "brittany", "abigail", "jane", "virginia", "lori",
    # Modern/Popular
    "sophia", "olivia", "isabella", "ava", "mia", "charlotte", "harper",
    "mila", "ella", "avery", "sofia",
    "camila", "aria", "scarlett", "luna", "chloe",
    "penelope", "layla", "riley", "zoey", "nora", "lily", "eleanor",
    "lillian", "addison", "aubrey", "ellie", "stella", "natalie", "zoe", "leah",
    "hazel", "violet", "aurora", "savannah", "audrey", "brooklyn", "bella",
    "claire", "skylar", "lucy", "paisley", "everly", "caroline", "nova",
    "genesis", "aaliyah", "kennedy", "kinsley", "allison", "maya",
    "madelyn", "adeline", "alexa", "ariana", "elena", "quinn", "mackenzie",
    "willow", "naomi",
    # Additional Common Names
    "alexis", "alice", "alina", "alison", "allison", "amanda", "amelia", "amy",
    "andrea", "angela", "anna", "annabelle", "aria", "ariana", "ashley", "athena",
    "audrey", "autumn", "ava", "avery", "bella", "brooklyn", "caitlin", "cameron",
    "caroline", "charlotte", "chloe", "claire", "clara", "daisy", "danielle",
    "delilah", "diana", "eleanor", "elena", "eliana", "elise", "elizabeth", "ella",
    "ellie", "emilia", "emily", "emma", "erica", "eva", "evelyn", "faith",
    "fiona", "gabriella", "gabrielle", "grace", "hailey", "hannah", "harper",
    "hazel", "helena", "isabella", "isabelle", "ivy", "jade", "jasmine", "jocelyn",
    "jordan", "josephine", "julia", "kaitlyn", "katherine", "kayla", "kennedy",
    "khloe", "kimberly", "laila", "lauren", "layla", "leah", "lillian", "lily",
    "linda", "lucy", "luna", "mackenzie", "madeline", "madelyn", "maya", "melissa",
    "mia", "mila", "naomi", "natalie", "nevaeh", "nicole", "nora", "olivia",
    "paige", "paisley", "penelope", "piper", "quinn", "rachel", "rebecca", "riley",
    "rose", "ruby", "ruth", "samantha", "sarah", "savannah", "scarlett", "serena",
    "skylar", "sofia", "sophia", "stella", "summer", "taylor", "valentina", "vanessa",
    "victoria", "violet", "vivian", "willow", "zoe", "zoey",
}

# Combined English Names
ENGLISH_NAMES = ENGLISH_MALE_NAMES | ENGLISH_FEMALE_NAMES


# ==================== CATEGORY 2: PERSIAN/FARSI NAMES (Persian Script) ====================

# Common Persian Male Names (in Persian script)
PERSIAN_MALE_NAMES = {
    # Traditional/Religious
    "علی", "محمد", "حسن", "حسین", "رضا", "امیر", "سعید", "مهدی", "احمد",
    "علی‌رضا", "علی‌اکبر", "علی‌اصغر", "علی‌محمد", "علی‌حسین",
    "محمدعلی", "محمدحسین", "محمدرضا", "محمدامین", "محمدجواد", "محمدحسن",
    "حسینعلی", "حسین‌رضا", "حسین‌محمد",
    "رضاعلی", "رضامحمد", "رضاحسین",
    "سعیدعلی", "سعیدمحمد", "سعیدرضا",
    "مهدی‌علی", "مهدی‌محمد", "مهدی‌رضا",
    "احمدعلی", "احمدمحمد", "احمدرضا",
    "امیرحسین", "امیرعلی", "امیرمحمد", "امیررضا",
    # Modern/Popular
    "پارسا", "آرین", "آریا", "کیان", "کامیار", "سینا", "نیما", "بنیامین",
    "دانیال", "یاسین", "ایلیا", "رایان", "آرمان", "آرمین", "آراد",
    "پویا", "پیمان", "پژمان", "پدرام", "پوریا",
    "تیمور", "حسام", "حسام‌الدین",
    "رامین", "سامان", "شایان", "عرفان", "فرهاد",
    "کامران", "کیوان", "مازیار",
    # Additional Common Persian Names
    "آرش", "آریا", "آرمان", "آرمین", "آرین", "آراد", "آرتا", "آرینا",
    "امیر", "امیرحسین", "امیرعلی", "امیرمحمد", "امیررضا", "امیرمهدی",
    "بنیامین", "بهرام", "بابک", "بهراد",
    "پارسا", "پویا", "پیمان", "پژمان", "پدرام", "پوریا", "پیمان",
    "تیمور", "تارا", "تیما",
    "حسام", "حسام‌الدین", "حسین", "حسن", "حسینعلی",
    "دانیال", "داریوش", "داوود",
    "رامین", "رایان", "رامتین", "راستین",
    "سامان", "سینا", "سپهر", "سروش", "سام", "سپند",
    "شایان", "شهریار", "شاهین", "شهاب",
    "عرفان", "علی", "علی‌رضا", "علی‌اکبر", "علی‌اصغر",
    "فرهاد", "فرید", "فرشاد", "فرزام", "فرزاد",
    "کامران", "کیوان", "کیارش", "کاوه",
    "مازیار", "مهدی", "محمدرضا", "محمدعلی", "محمدحسین", "مهدی‌علی",
    "نیما", "نوید", "نیما",
    "یاسین", "یاسر", "یونس",
}

# Common Persian Female Names (in Persian script)
PERSIAN_FEMALE_NAMES = {
    # Traditional/Religious
    "مریم", "فاطمه", "زهرا", "سارا", "نازنین", "نیلوفر", "مهسا", "سودابه",
    "پریسا", "نرگس", "فاطمه‌زهرا", "فاطمه‌سادات", "زهراسادات", "زهراخانم",
    "ساراخانم", "ساراسادات", "نازنین‌خانم", "نازنین‌سادات",
    "نیلوفرخانم", "نیلوفرسادات", "مهساخانم", "مهساسادات",
    "سودابه‌خانم", "سودابه‌سادات", "پریساخانم", "پریساسادات",
    "نرگس‌خانم", "نرگس‌سادات", "مریم‌سادات", "مریم‌خانم",
    # Modern/Popular
    "آرین", "آرینا", "آتوسا", "آیدا", "آناهیتا",
    "باران", "بهار", "پریا", "ترانه", "دلارام",
    "رؤیا", "سپیده", "شیدا", "غزل", "فرزانه",
    "کیمیا", "لیلا", "مبینا", "یاسمن",
    # Additional Common Persian Names
    "آرین", "آرینا", "آتوسا", "آیدا", "آناهیتا", "آرزو", "آرمان",
    "باران", "بهار", "بیتا", "بهناز", "بهاره",
    "پریسا", "پریا", "پگاه", "پردیس",
    "ترانه", "تارا", "تیما",
    "دلارام", "دلارا", "دلبر", "دلناز",
    "رؤیا", "رومینا", "رکسانا", "راضیه",
    "سارا", "سپیده", "سودابه", "سوسن", "سمیرا", "سحر", "سایه",
    "شیدا", "شهرزاد", "شهره", "شکوفه",
    "غزل", "غزاله", "گل", "گلناز", "گلنار",
    "فاطمه", "فاطمه‌زهرا", "فرزانه", "فریبا", "فریاد",
    "کیمیا", "کاملیا", "کاترینا",
    "لیلا", "لاله", "لیلی", "لیانا",
    "مبینا", "مهرناز", "مهرانه", "مهسا", "مهتاب", "مهدیس", "ملیسا",
    "نازنین", "نرگس", "نیلوفر", "نیلا", "نیکا", "نوشین",
    "یاسمن", "یاسمین", "یگانه",
}

# Combined Persian Names (Persian script)
PERSIAN_NAMES = PERSIAN_MALE_NAMES | PERSIAN_FEMALE_NAMES


# ==================== CATEGORY 3: ARABIC NAMES (Arabic Script) ====================

# Common Arabic Male Names (in Arabic script)
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
    "طارق", "زياد", "فادي", "مروان", "نادر", "وائل", "ياسر",
    # Additional Common Arabic Names
    "أحمد", "أمير", "أنس", "أيمن", "إبراهيم", "إسماعيل", "إسحاق",
    "باسم", "بسام", "بدر", "بلال",
    "تامر", "توفيق", "تمام",
    "جمال", "جهاد", "جواد",
    "حسام", "حسام‌الدين", "حسام", "حسني", "حكيم",
    "خالد", "خليل", "خيري",
    "داوود", "دانيال", "دينار",
    "رامي", "راشد", "رائد", "رامز",
    "سامي", "سالم", "سعد", "سعيد", "سلمان", "سهيل",
    "شريف", "شهاب", "شوقي",
    "طارق", "تمام", "توفيق",
    "عبدالله", "عبدالرحمن", "عبدالرحيم", "عبدالعزيز", "عبدالملك", "عبدالوهاب",
    "عبدالهادي", "عبدالرزاق", "عبدالستار", "عبدالغني", "عبدالكريم",
    "علي", "عمر", "عمرو", "عثمان", "عصام", "عمار",
    "فادي", "فارس", "فؤاد", "فهد", "فيصل",
    "قاسم", "قصي",
    "مالك", "مروان", "مصطفى", "موسى", "محمود", "محمد", "مهدي",
    "نادر", "ناصر", "نعيم", "نور الدين",
    "وائل", "وسام", "وليد",
    "ياسر", "ياسين", "يحيى", "يوسف", "يونس",
}

# Common Arabic Female Names (in Arabic script)
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
    "آمنة", "إيمان", "بسمة", "جمانة", "حبيبة",
    "دعاء", "رنا", "سجى", "شيماء", "ضحى",
    "كرمة", "هبة", "ياسمين",
    # Additional Common Arabic Names
    "آمنة", "آية", "أحلام", "أروى", "أسماء", "أمل", "أنس", "إيمان", "إيناس",
    "بسمة", "بثينة", "بتول", "بلقيس",
    "جمانة", "جنى", "جواهر",
    "حبيبة", "حليمة", "حنان", "حور",
    "خديجة", "خولة",
    "دعاء", "داليا", "دنيا", "دينا",
    "رنا", "رغد", "رنا", "رؤى", "راما", "ريم", "ريما",
    "زينب", "زينة", "زهراء", "زين",
    "سارة", "سجى", "سحر", "سلمى", "سما", "سميرة", "سندس", "سوسن",
    "شيماء", "شيرين", "شهد", "شذى",
    "ضحى", "ضياء",
    "عائشة", "عالية", "علياء", "عزة",
    "فاطمة", "فدوى", "فريدة", "فريال",
    "كرمة", "كاملة", "كندا",
    "ليلى", "لينا", "لارا", "لينا",
    "مريم", "مها", "مروة", "ميساء", "مريم", "منى", "مها",
    "نور", "نورا", "نادية", "نورين", "نعمة",
    "هبة", "هند", "هالة", "هناء",
    "ياسمين", "يسرى", "يافا",
}

# Combined Arabic Names (Arabic script)
ARABIC_NAMES = ARABIC_MALE_NAMES | ARABIC_FEMALE_NAMES


# ==================== CATEGORY 4: PERSIAN NAMES TRANSLITERATED (English Letters) ====================

# Persian Male Names written in English letters (transliterated)
PERSIAN_MALE_NAMES_TRANSLITERATED = {
    # Traditional/Religious
    "ali", "mohammad", "mohammed", "mohamad", "hasan", "hassan", "hossein", "hosein", "reza", "reza",
    "amir", "saeed", "saeid", "mahdi", "ahmad",
    "ali reza", "ali akbar", "ali asghar", "ali mohammad", "ali hossein",
    "mohammad ali", "mohammad hossein", "mohammad reza", "mohammad amin", "mohammad javad", "mohammad hasan",
    "hossein ali", "hossein reza", "hossein mohammad",
    "reza ali", "reza mohammad", "reza hossein",
    "saeed ali", "saeed mohammad", "saeed reza",
    "mahdi ali", "mahdi mohammad", "mahdi reza",
    "ahmad ali", "ahmad mohammad", "ahmad reza",
    "amirhossein", "amir hossein", "amir ali", "amir mohammad", "amir reza", "amir mahdi",
    # Modern/Popular
    "parsa", "arin", "arya", "aryan", "kian", "kamiar", "sina", "nima", "benyamin", "benjamin",
    "danial", "daniyal", "yasin", "ilya", "ryan", "arman", "armin", "arad", "arta", "arina",
    "pouya", "peyman", "pezhman", "pedram", "pouria",
    "timur", "tara", "tima",
    "hesam", "hesam aldin", "hossein", "hasan", "hossein ali",
    "ramin", "rayan", "ramtin", "rastin",
    "saman", "sina", "sepehr", "soroush", "sam", "sepand",
    "shayan", "shahriar", "shahin", "shahab",
    "erfan", "ali", "ali reza", "ali akbar", "ali asghar",
    "farhad", "farid", "farshad", "farzam", "farzad",
    "kamran", "keyvan", "kiarash", "kaveh",
    "maziar", "mahdi", "mohammad reza", "mohammad ali", "mohammad hossein", "mahdi ali",
    "nima", "navid",
    "yasin", "yaser", "younes",
}

# Persian Female Names written in English letters (transliterated)
PERSIAN_FEMALE_NAMES_TRANSLITERATED = {
    # Traditional/Religious
    "maryam", "fatemeh", "fatima", "zahra", "sara", "nazanin", "niloofar", "niloufar", "mehsa", "mahsa",
    "soodabeh", "parisa", "narges", "fatemeh zahra", "fatemeh sadat", "zahra sadat", "zahra khanom",
    "sara khanom", "sara sadat", "nazanin khanom", "nazanin sadat",
    "niloofar khanom", "niloofar sadat", "mehsa khanom", "mehsa sadat",
    "soodabeh khanom", "soodabeh sadat", "parisa khanom", "parisa sadat",
    "narges khanom", "narges sadat", "maryam sadat", "maryam khanom",
    # Modern/Popular
    "arin", "arina", "atoosa", "atousa", "ayda", "anahita", "arezoo", "armaan",
    "baran", "bahar", "beita", "behnaz", "bahareh",
    "parisa", "paria", "paghah", "pardis",
    "taraneh", "tara", "tima",
    "delaram", "delara", "delbar", "delnaz",
    "roya", "romina", "roxana", "razieh",
    "sara", "sepideh", "soodabeh", "susan", "samira", "sahar", "saye",
    "shida", "shahrzad", "shahreh", "shokoufeh",
    "ghazal", "ghazaleh", "gol", "golnaz", "golnar",
    "fatemeh", "fatemeh zahra", "farzaneh", "fariba", "faryad",
    "kimia", "kamellia", "katarina",
    "leila", "laleh", "lili", "liana",
    "mobina", "mehrnaz", "mehraneh", "mehsa", "mahtab", "mahdis", "melissa",
    "nazanin", "narges", "niloofar", "nila", "nika", "noushin",
    "yasaman", "yasmin", "yeganeh",
}

# Combined Persian Names Transliterated
PERSIAN_NAMES_TRANSLITERATED = PERSIAN_MALE_NAMES_TRANSLITERATED | PERSIAN_FEMALE_NAMES_TRANSLITERATED


# ==================== CATEGORY 5: ARABIC NAMES TRANSLITERATED (English Letters) ====================

# Arabic Male Names written in English letters (transliterated)
ARABIC_MALE_NAMES_TRANSLITERATED = {
    # Traditional/Religious
    "mohammad", "mohammed", "mohamad", "ahmad", "ali", "hasan", "hassan", "hussein", "hussain", "hosein",
    "abdullah", "abd allah", "khalid", "saad", "omar", "yusuf", "yousef",
    "mohammad ali", "mohammad hasan", "mohammad hussein", "mohammad abdullah", "mohammad khalid", "mohammad saad", "mohammad omar",
    "ahmad ali", "ahmad hasan", "ahmad hussein", "ahmad abdullah", "ahmad khalid", "ahmad saad", "ahmad omar",
    "ali mohammad", "ali ahmad", "ali hasan", "ali hussein", "ali abdullah", "ali khalid", "ali saad",
    "hasan mohammad", "hasan ahmad", "hasan ali", "hasan hussein", "hasan abdullah", "hasan khalid", "hasan saad",
    "hussein mohammad", "hussein ahmad", "hussein ali", "hussein hasan", "hussein abdullah", "hussein khalid", "hussein saad",
    "abdullah mohammad", "abdullah ahmad", "abdullah ali", "abdullah hasan", "abdullah hussein", "abdullah khalid", "abdullah saad",
    "khalid mohammad", "khalid ahmad", "khalid ali", "khalid hasan", "khalid hussein", "khalid abdullah", "khalid saad",
    "saad mohammad", "saad ahmad", "saad ali", "saad hasan", "saad hussein", "saad abdullah", "saad khalid",
    "omar mohammad", "omar ahmad", "omar ali", "omar hasan", "omar hussein", "omar abdullah", "omar khalid",
    "yusuf mohammad", "yusuf ahmad", "yusuf ali", "yusuf hasan", "yusuf hussein", "yusuf abdullah", "yusuf khalid",
    # Modern/Popular
    "abdul rahman", "abdul raheem", "abdul aziz", "abdul malik", "abdul wahab",
    "abdul hadi", "abdul razzaq", "abdul sattar", "abdul ghani", "abdul karim",
    "mahmoud", "mahmud", "mustafa", "mousa", "musa", "ibrahim", "ismail", "ishaq", "yaqub", "yakub",
    "tariq", "ziyad", "fadi", "marwan", "nader", "wael", "yasser",
    # Additional Common Arabic Names
    "amir", "anas", "ayman", "basem", "bassam", "badr", "bilal",
    "tamer", "tawfiq", "tamam",
    "jamal", "jihad", "jawad",
    "hesam", "hesam aldin", "hosni", "hakim",
    "khalil", "khairi",
    "dawud", "danial", "dinar",
    "rami", "rashed", "raed", "ramiz",
    "sami", "salem", "saeed", "salman", "suheil",
    "sharif", "shahab", "shawqi",
    "tamer", "tamam", "tawfiq",
    "abdul hadi", "abdul razzaq", "abdul sattar", "abdul ghani", "abdul karim",
    "amr", "othman", "issam", "ammar",
    "fadi", "faris", "fouad", "fahd", "faisal",
    "qasim", "qusay",
    "malik", "mohammad", "mahdi",
    "nader", "nasser", "naeem", "nur aldin",
    "wassam", "waleed",
    "yahya", "younes",
}

# Arabic Female Names written in English letters (transliterated)
ARABIC_FEMALE_NAMES_TRANSLITERATED = {
    # Traditional/Religious
    "fatima", "fatimah", "aisha", "aishah", "khadija", "khadijah", "maryam", "zainab", "zaynab", "sara", "sarah",
    "layla", "laila", "noor", "nur", "reem", "salma",
    "fatima zahra", "fatima saad", "fatima ali", "fatima hasan", "fatima hussein", "fatima abdullah", "fatima khalid",
    "aisha mohammad", "aisha ahmad", "aisha ali", "aisha hasan", "aisha hussein", "aisha abdullah", "aisha khalid",
    "khadija mohammad", "khadija ahmad", "khadija ali", "khadija hasan", "khadija hussein", "khadija abdullah", "khadija khalid",
    "maryam mohammad", "maryam ahmad", "maryam ali", "maryam hasan", "maryam hussein", "maryam abdullah", "maryam khalid",
    "zainab mohammad", "zainab ahmad", "zainab ali", "zainab hasan", "zainab hussein", "zainab abdullah", "zainab khalid",
    "sara mohammad", "sara ahmad", "sara ali", "sara hasan", "sara hussein", "sara abdullah", "sara khalid",
    "layla mohammad", "layla ahmad", "layla ali", "layla hasan", "layla hussein", "layla abdullah", "layla khalid",
    "noor mohammad", "noor ahmad", "noor ali", "noor hasan", "noor hussein", "noor abdullah", "noor khalid",
    "reem mohammad", "reem ahmad", "reem ali", "reem hasan", "reem hussein", "reem abdullah", "reem khalid",
    "salma mohammad", "salma ahmad", "salma ali", "salma hasan", "salma hussein", "salma abdullah", "salma khalid",
    # Modern/Popular
    "amena", "imane", "basma", "jamana", "habiba",
    "dua", "duaa", "rana", "saja", "shaima", "shayma", "duha",
    "karima", "hiba", "yasmin", "yasmine",
    # Additional Common Arabic Names
    "amena", "aya", "ahlam", "arwa", "asma", "amal", "anas", "imane", "inas",
    "basma", "buthaina", "batoul", "bilqis",
    "jamana", "jana", "jawahir",
    "habiba", "halima", "hanan", "hur",
    "khadija", "khawla",
    "dua", "dalia", "dunya", "dina",
    "rana", "raghad", "rua", "rama", "reem", "reema",
    "zainab", "zeina", "zahra", "zein",
    "sara", "saja", "sahar", "salma", "sama", "samira", "sundus", "susan",
    "shaima", "shirin", "shahd", "shatha",
    "duha", "diya",
    "aisha", "aliya", "aliyah", "izza",
    "fatima", "fadwa", "farida", "firyal",
    "karima", "kamila", "kinda",
    "layla", "lina", "lara",
    "maryam", "maha", "marwa", "maysa", "muna", "maha",
    "noor", "nora", "nadia", "nureen", "naima",
    "hiba", "hind", "hala", "hana",
    "yasmin", "yusra", "yafa",
}

# Combined Arabic Names Transliterated
ARABIC_NAMES_TRANSLITERATED = ARABIC_MALE_NAMES_TRANSLITERATED | ARABIC_FEMALE_NAMES_TRANSLITERATED


# ==================== CATEGORY 6: MIXED NAMES (English with Persian/Arabic Text) ====================

# Names that are English but may contain Persian/Arabic text or vice versa
MIXED_NAMES = {
    # English names commonly used in Persian/Arabic contexts
    "sara", "sarah", "maryam", "mary", "fatima", "fatimah", "ali", "ahmad", "mohammad",
    # Names that appear in both English and Persian/Arabic contexts
    "daniel", "danial", "daniyal", "benjamin", "benyamin", "ryan", "rayan",
    "lily", "lilya", "lila", "leila", "layla", "laila",
    "sophia", "sofia", "zoe", "zoe", "aria", "aria",
    "nora", "noor", "nur", "luna", "luna",
    # Common transliterations that might be mixed
    "alex", "alexander", "alexandra",
    "jasmine", "yasmin", "yasmine", "yasaman",
    "adam", "adham",
    "david", "dawud",
    "joseph", "yusuf", "yousef",
    "john", "yahya",
    "jesus", "isa",
    "michael", "mikail",
    "gabriel", "jibril",
    "noah", "nuh",
}


# ==================== ALL NAMES COMBINED (for comprehensive checking) ====================

# All names combined for general name detection
ALL_NAMES = (
    ENGLISH_NAMES |
    PERSIAN_NAMES |
    ARABIC_NAMES |
    PERSIAN_NAMES_TRANSLITERATED |
    ARABIC_NAMES_TRANSLITERATED |
    MIXED_NAMES
)


# ==================== HELPER FUNCTIONS ====================

def is_likely_name(text: str, language: str = "en") -> bool:
    """
    Check if text is likely a name based on comprehensive database.
    
    Args:
        text: User input text
        language: Language code ("en", "fa", "ar", "auto")
    
    Returns:
        bool: True if text is likely a name
    """
    text_clean = text.strip().lower()
    text_original = text.strip()  # Keep original for Persian/Arabic
    
    # Auto-detect language if requested
    if language == "auto":
        language = detect_language(text)
    
    # Check against name database based on language
    if language == "en":
        # Check English names and transliterated names
        return (text_clean in ENGLISH_NAMES or 
                text_clean in PERSIAN_NAMES_TRANSLITERATED or 
                text_clean in ARABIC_NAMES_TRANSLITERATED or
                text_clean in MIXED_NAMES)
    elif language == "fa":
        # Check Persian names (both script and transliterated)
        return (text_clean in PERSIAN_NAMES or 
                text_original in PERSIAN_NAMES or
                text_clean in PERSIAN_NAMES_TRANSLITERATED)
    elif language == "ar":
        # Check Arabic names (both script and transliterated)
        return (text_clean in ARABIC_NAMES or 
                text_original in ARABIC_NAMES or
                text_clean in ARABIC_NAMES_TRANSLITERATED)
    
    # Fallback: check all names
    if text_clean in ALL_NAMES or text_original in ALL_NAMES:
        return True
    
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


def get_name_category(name: str) -> str:
    """
    Get the category of a name.
    
    Args:
        name: Name to categorize
    
    Returns:
        str: Category name ("english", "persian", "arabic", "persian_transliterated", 
             "arabic_transliterated", "mixed", "unknown")
    """
    name_clean = name.strip().lower()
    name_original = name.strip()
    
    if name_clean in ENGLISH_NAMES:
        return "english"
    elif name_original in PERSIAN_NAMES or name_clean in PERSIAN_NAMES:
        return "persian"
    elif name_original in ARABIC_NAMES or name_clean in ARABIC_NAMES:
        return "arabic"
    elif name_clean in PERSIAN_NAMES_TRANSLITERATED:
        return "persian_transliterated"
    elif name_clean in ARABIC_NAMES_TRANSLITERATED:
        return "arabic_transliterated"
    elif name_clean in MIXED_NAMES:
        return "mixed"
    else:
        return "unknown"
