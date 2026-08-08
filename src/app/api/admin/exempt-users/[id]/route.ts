import { db } from '@/lib/db';
import { NextRequest, NextResponse } from 'next/server';

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;

    const existing = await db.exemptUser.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json(
        { error: 'کاربر معاف یافت نشد' },
        { status: 404 },
      );
    }

    await db.exemptUser.delete({ where: { id } });

    return NextResponse.json({ message: 'کاربر با موفقیت از لیست معافیت حذف شد' });
  } catch (error) {
    console.error('Exempt user delete error:', error);
    return NextResponse.json(
      { error: 'خطا در حذف کاربر معاف' },
      { status: 500 },
    );
  }
}
