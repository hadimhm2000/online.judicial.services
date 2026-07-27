"""
این فایل بخشی از تغییرات scenarios.py را نشان می‌دهد.
در تابع process_task، باید این بخش اضافه شود:

    # ── سناریوی اعلام وکالت ───────────────────────────────────────────────
    if task_type == "EALAM_VAKALAHT_SUBMIT":
        from ealam_vakalaht_scenario import process_ealam_vakalaht_task
        await process_ealam_vakalaht_task(data, bot)
        return

همچنین در browser_worker باید روتر اعلام وکالت include شود.
"""
