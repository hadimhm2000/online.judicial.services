

```python
@router.callback_query(F.data.startswith("okcart:"))
async def admin_approve_cart(callback: CallbackQuery, bot: Bot):
    # اصلاحیه امنیتی: بررسی ادمین
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔️ شما دسترسی به این عملیات را ندارید.", show_alert=True)
        return

    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    
    user_state = runtime_state.dp.fsm.resolve_context(bot, target_user_id, target_user_id)
    user_data = await user_state.get_data()
    
    cart = user_data.get("cart", [])
    photo_path = user_data.get('photo_path')
    
    for item in cart:
        q_type = item['query_type']
        tracking_code = item['tracking_code']
        doc_category = item.get('doc_category')
        doc_subcategory = item.get('doc_subcategory')
        need_attachments = item.get('need_attachments', False)
        
        doc_name = f"{doc_category} - {doc_subcategory}" if doc_subcategory else doc_category
        await log_event(
            "پرداخت", q_type, "تایید دستی سبد", target_user_id,
            tracking_code=tracking_code, doc_name=doc_name, payment_status="پرداخت شده (تایید دستی)"
        )
        
        await runtime_state.job_queue.put({
            'user_id': target_user_id, 
            'query_type': q_type, 
            'tracking_code': tracking_code, 
            'doc_category': doc_category, 
            'doc_subcategory': doc_subcategory, 
            'doc_type': doc_name,
            'need_attachments': need_attachments
        })
        
    await bot.send_message(
        target_user_id, 
        f"✅ **سبد خرید شما توسط مدیریت تایید شد.**\nتعداد {len(cart)} استعلام در صف قرار گرفت.",
        reply_markup=restart_kb
    )
    
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except:
            pass
            
    await user_state.clear()
    await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n✅ **تایید شد.**")
    await callback.answer("سبد خرید تایید شد.")
    
@router.callback_query(F.data.startswith("nocart:"))
async def admin_reject_cart(callback: CallbackQuery, bot: Bot):
    # اصلاحیه امنیتی: بررسی ادمین
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔️ شما دسترسی به این عملیات را ندارید.", show_alert=True)
        return

    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    
    user_state = runtime_state.dp.fsm.resolve_context(bot, target_user_id, target_user_id)
    user_data = await user_state.get_data()
    photo_path = user_data.get('photo_path')
    
    await bot.send_message(
        target_user_id, 
        "❌ **عدم تایید پرداخت سبد خرید:**\nفیش واریزی رد شد. لطفا رسید معتبر ارسال فرمایید.",
        reply_markup=restart_kb
    )
    
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except:
            pass
            
    await user_state.clear()
    await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n❌ **رد شد.**")
    await callback.answer("فیش رد شد.")


@router.callback_query(F.data.startswith("ok_stamp:"))
async def admin_approve_stamp(callback: CallbackQuery, bot: Bot):
    # اصلاحیه امنیتی: بررسی ادمین
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔️ شما دسترسی به این عملیات را ندارید.", show_alert=True)
        return

    await callback.answer()
    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    claim_amount = int(parts[2])

    try:
        from stamp_duty import calculate_stamp_duty, format_result_fa
        result = calculate_stamp_duty(claim_amount)
        result_text = format_result_fa(claim_amount, result)

        user_state = runtime_state.dp.fsm.resolve_context(bot, target_user_id, target_user_id)
        user_data = await user_state.get_data()
        photo_path = user_data.get("stamp_photo_path")
        await user_state.clear()

        await bot.send_message(
            target_user_id,
            f"✅ **پرداخت تایید شد (توسط مدیریت).**\n\n{result_text}",
            reply_markup=restart_kb,
            parse_mode="Markdown"
        )

        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass

        await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n✅ **تایید شد.**")
    except Exception as e:
        logging.error(f"[ADMIN_APPROVE_STAMP] خطا: {e}")
        await bot.send_message(ADMIN_ID, f"⚠️ خطا در تایید محاسبه تمبر کاربر {target_user_id}: {e}")


@router.callback_query(F.data.startswith("no_stamp:"))
async def admin_reject_stamp(callback: CallbackQuery, bot: Bot):
    # اصلاحیه امنیتی: بررسی ادمین
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔️ شما دسترسی به این عملیات را ندارید.", show_alert=True)
        return

    await callback.answer()
    parts = callback.data.split(":")
    target_user_id = int(parts[1])

    try:
        user_state = runtime_state.dp.fsm.resolve_context(bot, target_user_id, target_user_id)
        user_data = await user_state.get_data()
        photo_path = user_data.get("stamp_photo_path")
        await user_state.clear()

        await bot.send_message(
            target_user_id,
            "❌ رسید پرداخت تایید نشد. لطفاً مجدداً اقدام فرمایید.",
            reply_markup=restart_kb
        )

        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass

        await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n❌ **رد شد.**")
    except Exception as e:
        logging.error(f"[ADMIN_REJECT_STAMP] خطا: {e}")
        await bot.send_message(ADMIN_ID, f"⚠️ خطا در رد محاسبه تمبر کاربر {target_user_id}: {e}")
``` 