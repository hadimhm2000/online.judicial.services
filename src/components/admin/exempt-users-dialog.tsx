'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { ShieldCheck, UserPlus, UserX, Trash2, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface ExemptUser {
  id: string;
  telegramId: string;
  fullName: string | null;
   reason: string | null;
  createdAt: string;
  updatedAt: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ExemptUsersDialog({ open, onClose }: Props) {
  const [records, setRecords] = useState<ExemptUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [telegramId, setTelegramId] = useState('');
  const [fullName, setFullName] = useState('');
  const [reason, setReason] = useState('');

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/exempt-users');
      const data = await res.json();
      if (data.error) {
        toast.error(data.error);
        return;
      }
      setRecords(data.records);
    } catch {
      toast.error('خطا در دریافت اطلاعات');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchRecords();
      setTelegramId('');
      setFullName('');
      setReason('');
    }
  }, [open, fetchRecords]);

  const handleAdd = async () => {
    if (!telegramId.trim()) {
      toast.error('شناسه تلگرام الزامی است');
      return;
    }

    setAdding(true);
    try {
      const res = await fetch('/api/admin/exempt-users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          telegramId: telegramId.trim(),
          fullName: fullName.trim() || undefined,
          reason: reason.trim() || undefined,
        }),
      });

      const data = await res.json();

      if (res.status === 409) {
        toast.error(data.error);
        return;
      }
      if (data.error) {
        toast.error(data.error);
        return;
      }

      toast.success('کاربر با موفقیت به لیست معافیت اضافه شد');
      setTelegramId('');
      setFullName('');
      setReason('');
      fetchRecords();
    } catch {
      toast.error('خطا در ثبت کاربر');
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id: string) => {
    setDeleting(id);
    try {
      const res = await fetch(`/api/admin/exempt-users/${id}`, {
        method: 'DELETE',
      });

      const data = await res.json();

      if (data.error) {
        toast.error(data.error);
        return;
      }

      toast.success(data.message);
      fetchRecords();
    } catch {
      toast.error('خطا در حذف کاربر');
    } finally {
      setDeleting(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()} dir="rtl">
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="size-5" />
            لیست معافیت از پرداخت
          </DialogTitle>
          <DialogDescription>
            مدیریت کاربران معاف از پرداخت هزینه خدمات
          </DialogDescription>
        </DialogHeader>

        {/* Add form */}
        <div className="rounded-xl border bg-muted/30 p-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="exempt-telegram-id" className="text-sm">
                شناسه تلگرام <span className="text-destructive">*</span>
              </Label>
              <Input
                id="exempt-telegram-id"
                placeholder="مثال: 123456789"
                value={telegramId}
                onChange={(e) => setTelegramId(e.target.value)}
                dir="ltr"
                className="text-left font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="exempt-fullname" className="text-sm">
                نام و نام خانوادگی
              </Label>
              <Input
                id="exempt-fullname"
                placeholder="اختیاری"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="exempt-reason" className="text-sm">
              دلیل معافیت
            </Label>
            <Input
              id="exempt-reason"
              placeholder="اختیاری"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <div className="flex justify-start">
            <Button
              onClick={handleAdd}
              disabled={adding || !telegramId.trim()}
              size="sm"
              className="gap-1.5"
            >
              {adding ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <UserPlus className="size-4" />
              )}
              افزودن
            </Button>
          </div>
        </div>

        {/* List section */}
        <div className="mt-2">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          ) : records.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-8 text-muted-foreground">
              <UserX className="size-8" />
              <span className="text-sm">هیچ کاربر معافی ثبت نشده</span>
            </div>
          ) : (
            <div className="max-h-64 overflow-y-auto rounded-xl border custom-scrollbar">
              {records.map((user, index) => (
                <React.Fragment key={user.id}>
                  <div className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="rounded bg-muted px-2 py-0.5 font-mono text-sm">
                          {user.telegramId}
                        </span>
                        {user.fullName && (
                          <span className="text-sm font-medium">
                            {user.fullName}
                          </span>
                        )}
                      </div>
                      {user.reason && (
                        <p className="text-xs text-muted-foreground">
                          {user.reason}
                        </p>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className={cn(
                        'size-8 shrink-0 text-muted-foreground hover:text-red-600 hover:bg-red-50',
                        deleting === user.id && 'opacity-50',
                      )}
                      onClick={() => handleDelete(user.id)}
                      disabled={deleting === user.id}
                    >
                      {deleting === user.id ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Trash2 className="size-4" />
                      )}
                    </Button>
                  </div>
                  {index < records.length - 1 && <Separator />}
                </React.Fragment>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
