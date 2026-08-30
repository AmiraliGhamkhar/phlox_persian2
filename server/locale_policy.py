"""Product-language policy shared by every generated clinical response."""

PERSIAN_OUTPUT_INSTRUCTION = """زبان محصول فارسی است.
همه متن‌های توضیحی و بالینیِ خروجی را به فارسی معیار، حرفه‌ای و روان بنویس؛
ورودی ممکن است فارسی، انگلیسی یا ترکیبی از هر دو باشد. معنا، جزئیات بالینی،
نام بیمار، نام داروها، نام بیماری‌ها، مخفف‌های پزشکی، اعداد، واحدها، نام مدل،
کدها، شناسه‌ها و کلیدهای JSON را تغییر نده. اصطلاحات رایج پزشکی و نام داروها
را در صورت نیاز به همان شکل لاتین نگه دار و آن‌ها را ترجمه یا آوانویسی نکن.
این کار فقط پیاده‌سازی/بازنویسی است و هرگز ترجمه گفتار به زبان دیگر نیست.
اگر قالب یا JSON خواسته شده، همان قالب و کلیدهای فنی را دقیقاً حفظ کن و فقط
مقدارهای متنی را فارسی بنویس. از ارائه تشخیص قطعی یا توصیه درمانی خارج از
دستور سیستم خودداری کن."""


def add_persian_output_instruction(messages: list[dict]) -> list[dict]:
    """Return copied messages with the Persian output policy as a system rule."""
    prepared = [dict(message) for message in messages]
    for message in prepared:
        if message.get("role") == "system":
            content = message.get("content", "")
            if isinstance(content, str) and PERSIAN_OUTPUT_INSTRUCTION not in content:
                message["content"] = f"{content}\n\n{PERSIAN_OUTPUT_INSTRUCTION}"
            return prepared
    return [{"role": "system", "content": PERSIAN_OUTPUT_INSTRUCTION}, *prepared]
