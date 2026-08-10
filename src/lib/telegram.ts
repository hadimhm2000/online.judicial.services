import fs from 'fs';

const BOT_TOKEN = process.env.BOT_TOKEN;

// سرور ایرانی مستقیم به api.telegram.org دسترسی ندارد. اگر متغیر محیطی
// TELEGRAM_API_BASE تنظیم شده باشد (مثل پروکسی Cloudflare Worker که سمت
// ربات پایتون هم استفاده می‌شود)، از همان استفاده می‌کنیم.
const TELEGRAM_API_BASE = process.env.TELEGRAM_API_BASE || 'https://api.telegram.org';

function apiUrl(method: string) {
  if (!BOT_TOKEN) {
    throw new Error('BOT_TOKEN در فایل .env تنظیم نشده است');
  }
  return `${TELEGRAM_API_BASE}/bot${BOT_TOKEN}/${method}`;
}

/**
 * ارسال پیام متنی به کاربر از طریق ربات تلگرام.
 */
export async function sendTelegramMessage(chatId: string, text: string) {
  const res = await fetch(apiUrl('sendMessage'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text }),
  });

  const data = await res.json();
  if (!data.ok) {
    throw new Error(data.description || 'ارسال پیام تلگرام ناموفق بود');
  }
  return data;
}

/**
 * ارسال یک فایل (سند/تصویر) به کاربر از طریق ربات تلگرام.
 * filePath باید مسیر مطلق فایل روی دیسک سرور باشد.
 */
export async function sendTelegramDocument(
  chatId: string,
  filePath: string,
  fileName: string,
  caption?: string
) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`فایل روی سرور پیدا نشد: ${fileName}`);
  }

  const buffer = fs.readFileSync(filePath);
  const form = new FormData();
  form.append('chat_id', chatId);
  if (caption) form.append('caption', caption);
  form.append('document', new Blob([buffer]), fileName);

  const res = await fetch(apiUrl('sendDocument'), {
    method: 'POST',
    body: form,
  });

  const data = await res.json();
  if (!data.ok) {
    throw new Error(data.description || `ارسال فایل «${fileName}» ناموفق بود`);
  }
  return data;
}
