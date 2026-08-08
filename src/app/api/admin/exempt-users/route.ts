import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

export async function GET() {
  try {
    const records = await db.exemptUser.findMany({
      orderBy: { createdAt: 'desc' },
    });

    return NextResponse.json({ records, count: records.length });
  } catch (error) {
    console.error('Exempt users fetch error:', error);
    return NextResponse.json(
      { error: 'خطا در دریافت لیست معافیت' },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { telegramId, fullName, reason } = body as {
      telegramId?: string;
      fullName?: string;
      reason?: string;
    };

    if (!telegramId || typeof telegramId !== 'string' || telegramId.trim().length === 0) {
      return NextResponse.json(
        { error: 'شناسه تلگرام الزامی است' },
        { status: 400 },
      );
    }

    const trimmedId = telegramId.trim();

    const existing = await db.exemptUser.findUnique({
      where: { telegramId: trimmedId },
    });

    if (existing) {
      return NextResponse.json(
        { error: 'این کاربر قبلاً در لیست معافیت ثبت شده است' },
        { status: 409 },
      );
    }

    const record = await db.exemptUser.create({
      data: {
        telegramId: trimmedId,
        fullName: fullName?.trim() || null,
        reason: reason?.trim() || null,
      },
    });

    return NextResponse.json(record, { status: 201 });
  } catch (error) {
    console.error('Exempt user create error:', error);
    return NextResponse.json(
      { error: 'خطا در ثبت کاربر معاف' },
      { status: 500 },
    );
  }
}
