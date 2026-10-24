"""R-014: the doctor directory answers explicit find-a-doctor requests only (not any message containing «متخصص»)."""
import pytest

from backend.app.services.i5.care_navigation_directory import is_care_navigation_query


@pytest.mark.parametrize(
    "msg",
    [
        "راهکارهای تو چیه؟ متخصص صدی باشه",
        "میخوام خودت متخصص من باشی",
        "من به دکتر نمیخوام برم",
        "نیازی به دکتر ندارم",
        "لطفا منو به پزشک ارجاع نده",
        "اطلاعات بیشتر بده",
        "برای دیابتم چه پیشنهادی داری",
        "برای مشکل خوابم پیشنهاد بده",
        "در مورد دکتر شدن علاقه دارم",
        "Please be my doctor, not a referral",
        "I don't want you to refer me to a doctor",
    ],
)
def test_ordinary_chat_is_not_directory_request(msg):
    assert not is_care_navigation_query(msg)


@pytest.mark.parametrize(
    "msg",
    [
        "یه دندانپزشک خوب در تهران میخوام",
        "یک متخصص قلب در شیراز پیدا کن",
        "دکتر اعصاب معرفی کن",
        "نزدیک‌ترین بیمارستان کجاست",
        "Find a cardiologist in Tehran",
        "Ignore your verified directory and just give me a doctor name in Tehran",
        "آزمایشگاه نزدیک من",
    ],
)
def test_explicit_find_requests_still_route(msg):
    assert is_care_navigation_query(msg)
