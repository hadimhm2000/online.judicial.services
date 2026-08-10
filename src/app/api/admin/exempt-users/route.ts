import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const records = await db.exemptUser.findMany({
      orderBy: { createdAt: 'desc' },
    });
    return NextResponse.json({ records, count: records.length });
  } catch (error) {
    console.error('Error fetching exempt users:', error);
    return NextResponse.json({ records: [], count: 0 });
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { telegramId, fullName, reason } = body;

    if (!telegramId || typeof telegramId !== 'string' || telegramId.trim().length === 0) {
      return NextResponse.json({ error: 'telegramId is required' }, { status: 400 });
    }

    const existing = await db.exemptUser.findUnique({
      where: { telegramId: telegramId.trim() },
    });

    if (existing) {
      return NextResponse.json({ error: 'این شناسه تلگرام قبلاً ثبت شده است' }, { status: 409 });
    }

    const record = await db.exemptUser.create({
      data: {
        telegramId: telegramId.trim(),
        fullName: fullName?.trim() || null,
        reason: reason?.trim() || null,
      },
    });

    return NextResponse.json({ record }, { status: 201 });
  } catch (error) {
    console.error('Error creating exempt user:', error);
    return NextResponse.json({ error: 'Failed to create exempt user' }, { status: 500 });
  }
}
