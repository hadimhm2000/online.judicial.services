import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const telegramId = searchParams.get('telegramId');

    if (!telegramId) {
      return NextResponse.json({ error: 'telegramId is required' }, { status: 400 });
    }

    // Get all cases for this user
    const cases = await db.case.findMany({
      where: { telegramId },
      orderBy: { createdAt: 'desc' },
      take: 100,
    });

    // Compute summary
    const summary = {
      total: cases.length,
      completed: cases.filter((c) => c.status === 'COMPLETED').length,
      failed: cases.filter((c) => c.status === 'FAILED').length,
      unpaid: cases.filter((c) => c.feeStatus === 'UNPAID').length,
      totalSpent: cases.reduce((s, c) => s + (c.feeStatus === 'PAID' || c.feeStatus === 'MANUAL_APPROVED' ? c.fee : 0), 0),
      serviceTypes: [...new Set(cases.map((c) => c.serviceType))],
      lastActivity: cases[0]?.createdAt || null,
    };

    return NextResponse.json({ telegramId, fullName: cases[0]?.fullName || telegramId, summary, cases });
  } catch (error) {
    console.error('User history error:', error);
    return NextResponse.json({ error: 'Failed to fetch user history' }, { status: 500 });
  }
}
