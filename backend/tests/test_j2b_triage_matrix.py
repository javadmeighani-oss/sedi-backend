"""J2b (R-065, D-404): the triage precision matrix. Ordinary conversation must NEVER receive a medical hint; real complaints and
emergencies must. One table per language - every future false positive is added HERE instead of waiting for a review round."""
import pytest

from backend.app.services.care_navigation.symptom_triage import llm_hint, triage

QUIET = [  # (text, lang) -> no hint at all
    # Persian: acknowledgements, idioms, feelings, ordinary words that contain body words
    ("چشم، حتماً", "fa"), ("چشم ممنون", "fa"), ("دستت درد نکنه", "fa"), ("دست شما درد نکنه، ممنون", "fa"), ("سرم شلوغه امروز", "fa"),
    ("قلبم برات می‌تپه", "fa"), ("دلم برات تنگ شده", "fa"), ("دلم گرفته", "fa"), ("قلبم شکست", "fa"), ("ببینیم فردا چه می‌شود", "fa"),
    ("حرف زدن با پدرم سخت است", "fa"), ("امروز یک فیلم دیدم", "fa"), ("سلام، حالت چطوره؟", "fa"), ("فردا ساعت پنج جلسه دارم", "fa"),
    ("کمرمو راست کردم و رفتم", "fa"), ("پوست پرتقال رو بکن", "fa"), ("جوش شیرین می‌خوام", "fa"), ("خونه‌ی ما نزدیک بیمارستان است", "fa"),
    ("دکتر دیروز گفت خوبی", "fa"), ("سرکار خانم دکتر، ممنون", "fa"),
    # English
    ("thanks, see you tomorrow", "en"), ("this project is a real headache for the team", "en"), ("he is a pain in the neck", "en"),
    ("my heart is broken, that movie was sad", "en"), ("the trial period ends tomorrow", "en"), ("I passed outside the shop", "en"),
    ("what does heavy bleeding mean?", "en"), ("I never fainted", "en"), ("I fainted as a child", "en"), ("suddenly lost my keys", "en"),
    ("I have a meeting at five", "en"), ("the rash decision cost us", "en"), ("I need a break from work", "en"),
    # Arabic
    ("شكراً جزيلاً", "ar"), ("نلتقي غداً إن شاء الله", "ar"), ("قلبي معك", "ar"), ("يعطيك العافية", "ar"), ("مرحباً كيف حالك", "ar"),
]

HINTED = [  # (text, lang) -> some hint (emergency or routine)
    ("سردرد دارم", "fa"), ("چشمم درد می‌کنه", "fa"), ("زانوم درد می‌کنه", "fa"), ("معده‌ام می‌سوزد", "fa"), ("پوستم خارش دارد", "fa"),
    ("بینی‌ام گرفته", "fa"), ("تب بالا دارم", "fa"), ("قاعدگی‌ام نامنظم است", "fa"), ("یه چیزی‌ام هست ولی نمی‌دانم چیست", "fa"),
    ("خونریزی شدید دارم", "fa"), ("غش کردم", "fa"), ("قفسه سینه‌ام درد می‌کند و نفسم تنگ شده", "fa"), ("دیدم ناگهان تار شده", "fa"),
    ("my knee hurts", "en"), ("I have a headache", "en"), ("I have palpitations", "en"), ("I have a high fever", "en"),
    ("my period is late", "en"), ("I fainted", "en"), ("I can't breathe", "en"), ("heavy bleeding that won't stop", "en"),
    ("I have had heavy bleeding since last month", "en"), ("I feel sick", "en"), ("my vision suddenly went black, what does that mean?", "en"),
    ("عندي صداع", "ar"), ("أشعر بألم في صدري ولا أستطيع التنفس", "ar"), ("ركبتي تؤلمني", "ar"), ("أحتاج طبيباً لعيني", "ar"),
    ("لدي حمى شديدة", "ar"), ("فقدت الوعي", "ar"),
]


@pytest.mark.parametrize("text, lang", QUIET)
def test_ordinary_conversation_gets_no_medical_hint(text, lang):
    assert llm_hint(triage(text, lang)) is None


@pytest.mark.parametrize("text, lang", HINTED)
def test_real_complaints_and_emergencies_get_a_hint(text, lang):
    assert llm_hint(triage(text, lang)) is not None
