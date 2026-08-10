import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const message = await db.botMessage.findUnique({ where: { id } });
    if (!message) {
      return NextResponse.json({ error: 'پیام یافت نشد' }, { status: 404 });
    }

    // Simulate sending via Telegram bot API
    // In production, this would call the actual Telegram Bot API
    // POST https://api.telegram.org/bot{TOKEN}/sendMessage with chat_id and text
    const sentSuccessfully = true; // Placeholder for actual bot integration

    if (sentSuccessfully) {
      const updated = await db.botMessage.update({
        where: { id },
        data: {
          status: 'SENT',
          sentAt: new Date(),
        },
      });

      await db.activityLog.create({
        data: {
          action: 'BOT_MESSAGE_SENT',
          details: `پیام ارسال شد برای ${message.fullName || message.telegramId}`,
        },
      });

      return NextResponse.json(updated);
    } else {
      await db.botMessage.update({
        where: { id },
        data: {
          status: 'FAILED',
          errorDetails: 'خطا در ارتباط با سرور تلگرام',
        },
      });

      return NextResponse.json({ error: 'خطا در ارسال پیام' }, { status: 500 });
    }
  } catch (error) {
    console.error('Bot message send error:', error);
    return NextResponse.json({ error: 'خطا در ارسال پیام' }, { status: 500 });
  }
}
