import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AppErrorBoundary } from "../components/common/AppErrorBoundary";
import { translatePersian } from "../i18n/fa";

function Boom() {
    throw new Error("kaboom");
}

describe("AppErrorBoundary", () => {
    it("renders children when nothing throws", () => {
        render(
            <AppErrorBoundary>
                <p>ok child</p>
            </AppErrorBoundary>,
        );
        expect(screen.getByText("ok child")).toBeInTheDocument();
    });

    it("shows a Persian recovery card instead of a blank screen on crash", () => {
        // Silence the expected console.error from React during this test.
        const spy = vi.spyOn(console, "error").mockImplementation(() => {});
        render(
            <AppErrorBoundary>
                <Boom />
            </AppErrorBoundary>,
        );
        expect(
            screen.getByText("مشکلی در نمایش این صفحه رخ داد"),
        ).toBeInTheDocument();
        expect(screen.getByRole("alert")).toBeInTheDocument();
        expect(screen.getByText("بارگذاری مجدد برنامه")).toBeInTheDocument();
        spy.mockRestore();
    });
});

describe("Persian UI copy coverage (user-facing leaks)", () => {
    it.each([
        ["No files found.", "فایلی پیدا نشد."],
        ["No tasks yet.", "هنوز کاری ثبت نشده است."],
        [
            "Are you sure you want to leave this page? Unsaved changes will be lost.",
            "آیا مطمئنید می‌خواهید این صفحه را ترک کنید؟ تغییرات ذخیره‌نشده از بین می‌روند.",
        ],
        [
            "Enter your passphrase to decrypt and access your patient data.",
            "برای رمزگشایی و دسترسی به داده‌های بیماران، عبارت عبور خود را وارد کنید.",
        ],
        ["Est. time", "زمان تقریبی"],
        [
            "Phlox may make mistakes. Always verify critical information.",
            "فلوکس ممکن است اشتباه کند. همیشه اطلاعات مهم را بررسی کنید.",
        ],
    ])("translates %s", (english, persian) => {
        expect(translatePersian(english)).toBe(persian);
    });

    it("translates the runtime-built request timeout description", () => {
        expect(
            translatePersian(
                "The request took too long to complete (30s timeout)",
            ),
        ).toContain("مهلت ۳۰ ثانیه");
    });
});
