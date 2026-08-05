#!/usr/bin/env python3
"""
اسکریپت رفع خودکار باگ «بازگشت به منوی اصلی»
──────────────────────────────────────────────────
مشکل: همه جایی که state.clear() صدا زده می‌شود و سپس main_menu_kb
       نمایش داده می‌شود، باید await state.set_state(Form.main_menu)
       نیز اضافه شود.

اجرا: python fix_back_to_menu.py
"""

import re
import sys
import shutil
from pathlib import Path

FILES_TO_FIX = [
    "lavayeh_handlers.py",
    "ezhharnameh_handlers.py",
    "stamp_calc_handlers.py",
    "handlers.py",
]

# ─── Pattern شناسایی مشکل ────────────────────────────────────────────────────
# هر جایی که:
#  1. state.clear() صدا زده می‌شود
#  2. بعد از آن (در چند خط) main_menu_kb استفاده شده
#  3. اما set_state(Form.main_menu) وجود ندارد


def fix_file(filepath: Path) -> tuple[int, str]:
    """
    فایل را می‌خواند، الگوهای معیوب را پیدا و اصلاح می‌کند.
    برمی‌گرداند: (تعداد اصلاح‌ها, محتوای اصلاح‌شده)
    """
    content = filepath.read_text(encoding="utf-8")
    original = content
    count = 0

    # ─── اصلاح ۱: state.clear() بدون set_state بعد از آن
    # الگو: await state.clear() که در ۳ خط بعد main_menu_kb دارد ولی set_state ندارد
    lines = content.split("\n")
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # تشخیص خط state.clear()
        clear_match = re.match(r"^(\s*)await\s+state\.clear\(\)\s*$", line)
        if clear_match:
            indent = clear_match.group(1)

            # بررسی: آیا خط بعدی set_state دارد؟
            next_lines_text = "\n".join(lines[i+1:i+6])
            has_set_state = "set_state(Form.main_menu)" in next_lines_text
            has_main_menu_kb = "main_menu_kb" in next_lines_text

            if has_main_menu_kb and not has_set_state:
                # اضافه کردن set_state بعد از clear()
                new_lines.append(line)
                new_lines.append(
                    f"{indent}await state.set_state(Form.main_menu)"
                    f"  # ← FIX: state باید Form.main_menu باشد نه None"
                )
                count += 1
                i += 1
                continue

        new_lines.append(line)
        i += 1

    fixed_content = "\n".join(new_lines)
    return count, fixed_content


def check_imports(content: str, filename: str) -> str:
    """بررسی و اضافه کردن import های لازم"""
    
    # برای stamp_calc_handlers.py باید main_menu_kb import شود
    if "stamp_calc_handlers.py" in filename:
        if "main_menu_kb" not in content and "from keyboards import" in content:
            content = re.sub(
                r"(from keyboards import [^\n]+)",
                lambda m: m.group(0).rstrip() + ", main_menu_kb"
                if "main_menu_kb" not in m.group(0)
                else m.group(0),
                content,
                count=1
            )
            print(f"  ➕ main_menu_kb به imports اضافه شد")

    return content


def main():
    print("=" * 65)
    print("🔧 رفع خودکار باگ «بازگشت به منوی اصلی»")
    print("=" * 65)

    total_fixes = 0
    files_fixed = []

    for filename in FILES_TO_FIX:
        filepath = Path(filename)
        if not filepath.exists():
            print(f"\n⚠️  فایل '{filename}' پیدا نشد — رد شد")
            continue

        print(f"\n📄 پردازش: {filename}")

        # پشتیبان‌گیری
        backup_path = filepath.with_suffix(".py.bak")
        shutil.copy2(filepath, backup_path)
        print(f"  💾 پشتیبان ذخیره شد: {backup_path.name}")

        # اصلاح فایل
        fix_count, fixed_content = fix_file(filepath)

        # بررسی imports
        fixed_content = check_imports(fixed_content, filename)

        if fix_count > 0 or fixed_content != filepath.read_text(encoding="utf-8"):
            filepath.write_text(fixed_content, encoding="utf-8")
            print(f"  ✅ {fix_count} مورد اصلاح شد")
            total_fixes += fix_count
            files_fixed.append(filename)
        else:
            print(f"  ℹ️  مشکلی پیدا نشد یا قبلاً اصلاح شده")

    print("\n" + "=" * 65)
    if total_fixes > 0:
        print(f"✅ جمعاً {total_fixes} مورد در {len(files_fixed)} فایل اصلاح شد:")
        for f in files_fixed:
            print(f"   • {f}")
        print("\n⚠️  لطفاً فایل‌ها را بررسی کنید و بعد ربات را ریستارت کنید.")
    else:
        print("ℹ️  هیچ تغییری اعمال نشد.")
    print("=" * 65)


if __name__ == "__main__":
    main()
