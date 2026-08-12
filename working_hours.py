"""
بررسی ساعت کاری ربات — بازه ثابت ۱۰ الی ۲۲ برای همه روزها.
"""
import datetime

TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))

START_HOUR = 10
END_HOUR = 22


async def is_within_working_hours():
    """
    برمی‌گرداند: (در_بازه‌ی_کاری: bool, تنظیمات_امروز: dict)
    """
    tehran_time = datetime.datetime.now(TEHRAN_TZ)
    now_minutes = tehran_time.hour * 60 + tehran_time.minute
    start_minutes = START_HOUR * 60
    end_minutes = END_HOUR * 60

    return (
        start_minutes <= now_minutes < end_minutes,
        {"startHour": START_HOUR, "endHour": END_HOUR, "enabled": True},
    )