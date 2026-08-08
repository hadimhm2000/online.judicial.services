'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Clock, Loader2, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface WorkingHourItem {
  dayOfWeek: number;
  startHour: number;
  startMin: number;
  endHour: number;
  endMin: number;
  enabled: boolean;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

const DAY_NAMES = [
  'شنبه',
  'یکشنبه',
  'دوشنبه',
  'سه‌شنبه',
  'چهارشنبه',
  'پنجشنبه',
  'جمعه',
] as const;

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const MINUTES = [0, 15, 30, 45];

function toPersianNum(n: number): string {
  return n.toLocaleString('fa-IR');
}

function padTwo(n: number): string {
  return n.toString().padStart(2, '0');
}

export default function WorkingHoursDialog({ open, onClose }: Props) {
  const [schedule, setSchedule] = useState<WorkingHourItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchSchedule = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/working-hours');
      const data = await res.json();
      if (data.error) {
        toast.error(data.error);
        return;
      }
      setSchedule(data.schedule);
    } catch {
      toast.error('خطا در دریافت اطلاعات');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchSchedule();
    }
  }, [open, fetchSchedule]);

  const updateDay = (dayOfWeek: number, patch: Partial<WorkingHourItem>) => {
    setSchedule((prev) =>
      prev.map((item) =>
        item.dayOfWeek === dayOfWeek ? { ...item, ...patch } : item,
      ),
    );
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/admin/working-hours', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schedule }),
      });
      const data = await res.json();
      if (data.error) {
        toast.error(data.error);
        return;
      }
      toast.success('ساعت کاری با موفقیت ذخیره شد');
      onClose();
    } catch {
      toast.error('خطا در ذخیره‌سازی');
    } finally {
      setSaving(false);
    }
  };

  const handleApplyToAll = () => {
    const firstEnabled = schedule.find((d) => d.enabled);
    if (!firstEnabled) {
      toast.error('هیچ روز فعالی یافت نشد');
      return;
    }
    setSchedule((prev) =>
      prev.map((item) =>
        item.enabled
          ? {
              ...item,
              startHour: firstEnabled.startHour,
              startMin: firstEnabled.startMin,
              endHour: firstEnabled.endHour,
              endMin: firstEnabled.endMin,
            }
          : item,
      ),
    );
    toast.success('برنامه روز اول به همه روزهای فعال اعمال شد');
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()} dir="rtl">
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Clock className="size-5" />
            تنظیم ساعت کاری ربات
          </DialogTitle>
          <DialogDescription>
            ساعت شروع و پایان کاری ربات را برای هر روز هفته مشخص کنید.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="max-h-96 overflow-y-auto space-y-3 pr-1 custom-scrollbar">
            {schedule.map((day) => (
              <div
                key={day.dayOfWeek}
                className={cn(
                  'flex flex-col sm:flex-row sm:items-center gap-3 rounded-lg border p-4 transition-colors',
                  !day.enabled && 'bg-muted/30',
                )}
              >
                {/* Day name and switch */}
                <div className="flex items-center gap-3 sm:w-36 shrink-0">
                  <Switch
                    checked={day.enabled}
                    onCheckedChange={(checked) =>
                      updateDay(day.dayOfWeek, { enabled: checked })
                    }
                  />
                  <span
                    className={cn(
                      'text-sm font-medium',
                      !day.enabled && 'text-muted-foreground',
                    )}
                  >
                    {DAY_NAMES[day.dayOfWeek]}
                  </span>
                </div>

                {/* Time selectors */}
                <div
                  className={cn(
                    'flex items-center gap-2 flex-wrap',
                    !day.enabled && 'opacity-40 pointer-events-none',
                  )}
                >
                  <span className="text-xs text-muted-foreground">از</span>
                  <Select
                    value={String(day.startHour)}
                    onValueChange={(v) =>
                      updateDay(day.dayOfWeek, { startHour: Number(v) })
                    }
                  >
                    <SelectTrigger className="w-20" size="sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HOURS.map((h) => (
                        <SelectItem key={h} value={String(h)}>
                          {toPersianNum(h)}:۰۰
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select
                    value={String(day.startMin)}
                    onValueChange={(v) =>
                      updateDay(day.dayOfWeek, { startMin: Number(v) })
                    }
                  >
                    <SelectTrigger className="w-20" size="sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MINUTES.map((m) => (
                        <SelectItem key={m} value={String(m)}>
                          :{toPersianNum(padTwo(m))}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <span className="text-xs text-muted-foreground mr-1">تا</span>

                  <Select
                    value={String(day.endHour)}
                    onValueChange={(v) =>
                      updateDay(day.dayOfWeek, { endHour: Number(v) })
                    }
                  >
                    <SelectTrigger className="w-20" size="sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HOURS.map((h) => (
                        <SelectItem key={h} value={String(h)}>
                          {toPersianNum(h)}:۰۰
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select
                    value={String(day.endMin)}
                    onValueChange={(v) =>
                      updateDay(day.dayOfWeek, { endMin: Number(v) })
                    }
                  >
                    <SelectTrigger className="w-20" size="sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MINUTES.map((m) => (
                        <SelectItem key={m} value={String(m)}>
                          :{toPersianNum(padTwo(m))}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ))}
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleApplyToAll}
            disabled={saving || loading}
            className="gap-1.5"
          >
            <Copy className="size-4" />
            اعمال به همه
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving || loading}
            className="gap-1.5"
          >
            {saving && <Loader2 className="size-4 animate-spin" />}
            ذخیره
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
