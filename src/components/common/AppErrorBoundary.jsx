import React from "react";
import { translatePersian, toPersianDigits } from "../../i18n/fa";

/**
 * Last-line-of-defense error boundary.
 *
 * Without it, a render exception anywhere in the tree unmounts the whole
 * app and the user is left with a blank white screen. This boundary renders
 * a calm, Persian recovery card instead, offering a retry (re-renders the
 * tree) and a reload (fresh JS + state). It deliberately avoids Chakra
 * components and router context so it still renders when those themselves
 * failed; it lives above the Router in index.jsx.
 */
const wrapper = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: "100dvh",
    padding: "24px",
    background: "var(--chakra-colors-bg, #1a1b26)",
    color: "var(--chakra-colors-fg, #c0caf5)",
    fontFamily: '"Vazirmatn", Tahoma, Arial, sans-serif',
    textAlign: "center",
};

const card = {
    maxWidth: "560px",
    width: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "16px",
    padding: "40px 32px",
    borderRadius: "24px",
    border: "1px solid rgba(128, 128, 128, 0.25)",
    boxShadow: "0 24px 60px rgba(0, 0, 0, 0.35)",
};

const heading = { fontSize: "22px", fontWeight: 700, margin: 0 };
const body = { fontSize: "15px", lineHeight: 1.8, margin: 0, opacity: 0.85 };

const buttonRow = { display: "flex", gap: "12px", flexWrap: "wrap", justifyContent: "center" };

const primaryBtn = {
    padding: "10px 22px",
    borderRadius: "999px",
    border: "none",
    background: "#3fa57f",
    color: "#ffffff",
    font: "inherit",
    fontWeight: 700,
    cursor: "pointer",
};

const secondaryBtn = {
    padding: "10px 22px",
    borderRadius: "999px",
    border: "1px solid rgba(128, 128, 128, 0.45)",
    background: "transparent",
    color: "inherit",
    font: "inherit",
    fontWeight: 600,
    cursor: "pointer",
};

const details = {
    direction: "ltr",
    textAlign: "left",
    width: "100%",
    fontSize: "12px",
    color: "inherit",
    opacity: 0.7,
};

const code = {
    display: "block",
    marginTop: "8px",
    padding: "12px",
    borderRadius: "12px",
    background: "rgba(128, 128, 128, 0.12)",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    maxHeight: "180px",
    overflowY: "auto",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

export class AppErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { error: null, errorCount: 0 };
        this.handleRetry = this.handleRetry.bind(this);
    }

    static getDerivedStateFromError(error) {
        return { error };
    }

    componentDidCatch(error, info) {
        // Keep the original stack in the console for debugging; the user
        // only ever sees the recovery card. Count repeats so we can nudge
        // toward a reload when "try again" keeps failing.
        console.error("Phlox render error:", error, info?.componentStack);
        this.setState((prev) => ({ errorCount: prev.errorCount + 1 }));
    }

    handleRetry() {
        // Resetting the error state re-renders the subtree. If the failure
        // is persistent the user gets a clear nudge to reload instead.
        this.setState({ error: null });
    }

    render() {
        if (!this.state.error) return this.props.children;

        const message = String(
            this.state.error?.message ||
                translatePersian("An unexpected error occurred."),
        );
        const repeated = this.state.errorCount > 1;

        return (
            <div style={wrapper} role="alert" aria-live="assertive">
                <div style={card}>
                    <div style={{ fontSize: "40px", lineHeight: 1 }} aria-hidden="true">
                        ⚠️
                    </div>
                    <h1 style={heading}>مشکلی در نمایش این صفحه رخ داد</h1>
                    <p style={body}>
                        {repeated
                            ? "این خطا دوباره تکرار شد. لطفاً برنامه را دوباره بارگذاری کنید. اگر مشکل ادامه داشت، داده‌های شما محفوظ است و می‌توانید بعداً دوباره تلاش کنید."
                            : "داده‌های شما محفوظ است. برای ادامه، دوباره تلاش کنید یا برنامه را بارگذاری مجدد کنید."}
                    </p>
                    <div style={buttonRow}>
                        {!repeated && (
                            <button type="button" style={primaryBtn} onClick={this.handleRetry}>
                                تلاش دوباره
                            </button>
                        )}
                        <button
                            type="button"
                            style={repeated ? primaryBtn : secondaryBtn}
                            onClick={() => window.location.reload()}
                        >
                            بارگذاری مجدد برنامه
                        </button>
                        <button
                            type="button"
                            style={secondaryBtn}
                            onClick={() => {
                                // Same-document path only: absolute URLs would
                                // break the packaged Tauri webview origin.
                                window.location.pathname = "/";
                            }}
                        >
                            بازگشت به صفحه اصلی
                        </button>
                    </div>
                    <details style={details}>
                        <summary>جزئیات فنی ({toPersianDigits(new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }))})</summary>
                        <code style={code}>{message}</code>
                    </details>
                </div>
            </div>
        );
    }
}

export default AppErrorBoundary;
