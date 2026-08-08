import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

const DEFAULT_SCHEDULE = [
  { dayOfWeek: 0, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 1, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 2, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 3, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 4, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 5, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
  { dayOfWeek: 6, startHour: 8, startMin: 0, endHour: 22, endMin: 0, enabled: true },
];

export async function GET() {
  try {
    const records = await db.workingHour.findMany({
      orderBy: { dayOfWeek: 'asc' },
    });

    if (records.length === 0) {
      return NextResponse.json({ schedule: DEFAULT_SCHEDULE });
    }

    const schedule = records.map((r) => ({
      dayOfWeek: r.dayOfWeek,
      startHour: r.startHour,
      startMin: r.startMin,
      endHour: r.endHour,
      endMin: r.endMin,
      enabled: r.enabled,
    }));

    return NextResponse.json({ schedule });
  } catch (error) {
    console.error('Working hours fetch error:', error);
    return NextResponse.json(
      { error: 'خطا در دریافت ساعت کاری' },
      { status: 500 },
    );
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const items: {
      dayOfWeek: number;
      startHour: number;
      startMin: number;
      endHour: number;
      endMin: number;
      enabled: boolean;
    }[] = body.schedule;

    if (!Array.isArray(items) || items.length === 0) {
      return NextResponse.json(
        { error: 'داده‌های نامعتبر' },
        { status: 400 },
      );
    }

    for (const item of items) {
      if (
        typeof item.dayOfWeek !== 'number' ||
        item.dayOfWeek < 0 ||
        item.dayOfWeek > 6
      ) {
        return NextResponse.json(
          { error: 'روز هفته نامعتبر است' },
          { status: 400 },
        );
      }
      if (
        typeof item.startHour !== 'number' ||
        item.startHour < 0 ||
        item.startHour > 23
      ) {
        return NextResponse.json(
          { error: 'ساعت شروع نامعتبر است' },
          { status: 400 },
        );
      }
      if (
        typeof item.endHour !== 'number' ||
        item.endHour < 0 ||
        item.endHour > 23
      ) {
        return NextResponse.json(
          { error: 'ساعت پایان نامعتبر است' },
          { status: 400 },
        );
      }
      if (
        typeof item.startMin !== 'number' ||
        item.startMin < 0 ||
        item.startMin > 59
      ) {
        return NextResponse.json(
          { error: 'دقیقه شروع نامعتبر است' },
          { status: 400 },
        );
      }
      if (
        typeof item.endMin !== 'number' ||
        item.endMin < 0 ||
        item.endMin > 59
      ) {
        return NextResponse.json(
          { error: 'دقیقه پایان نامعتبر است' },
          { status: 400 },
        );
      }
    }

    for (const item of items) {
      await db.workingHour.upsert({
        where: { dayOfWeek: item.dayOfWeek },
        update: {
          startHour: item.startHour,
          startMin: item.startMin,
          endHour: item.endHour,
          endMin: item.endMin,
          enabled: item.enabled,
        },
        create: {
          dayOfWeek: item.dayOfWeek,
          startHour: item.startHour,
          startMin: item.startMin,
          endHour: item.endHour,
          endMin: item.endMin,
          enabled: item.enabled,
        },
      });
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Working hours update error:', error);
    return NextResponse.json(
      { error: 'خطا در ذخیره ساعت کاری' },
      { status: 500 },
    );
  }
}
