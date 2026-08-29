import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./utils";
import PendingActionCard from "../components/common/PendingActionCard";

// Harness that reproduces the real parent contract: the card mutates
// message.confirmations[i].status through setMessages and re-renders from it.
function CardHarness({ confirmation }) {
    const [messages, setMessages] = useState([
        { role: "assistant", content: "" },
        { role: "assistant", content: "", confirmations: [confirmation] },
    ]);
    const current = messages[1].confirmations[0];
    return (
        <div>
            {messages.map((m, i) => (
                <p key={i}>{m.content}</p>
            ))}
            <PendingActionCard
                confirmation={current}
                setMessages={setMessages}
                messageIndex={1}
                confIndex={0}
            />
        </div>
    );
}

const confirmPendingAction = vi.fn();
const cancelPendingAction = vi.fn();

vi.mock("../utils/api/chatApi", () => ({
    chatApi: {
        get confirmPendingAction() {
            return confirmPendingAction;
        },
        get cancelPendingAction() {
            return cancelPendingAction;
        },
    },
}));

describe("PendingActionCard", () => {
    const baseConfirmation = {
        actionId: "act-1",
        tool: "create_note",
        summary: "یادداشت برای بیمار teste ذخیره شود",
        status: "pending",
    };

    beforeEach(() => {
        confirmPendingAction.mockReset();
        cancelPendingAction.mockReset();
    });

    afterEach(() => {
        cleanup();
        vi.restoreAllMocks();
    });

    it("renders the summary with approve/cancel controls while pending", () => {
        renderWithProviders(
            <PendingActionCard
                confirmation={baseConfirmation}
                setMessages={vi.fn()}
                messageIndex={1}
                confIndex={0}
            />,
        );

        expect(screen.getByText("نیاز به تأیید شما")).toBeInTheDocument();
        expect(screen.getByText(/teste/)).toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: "تأیید و اجرا" }),
        ).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "لغو" })).toBeInTheDocument();
    });

    it("marks the card done after a successful approval", async () => {
        confirmPendingAction.mockResolvedValue({ result: "ok" });

        renderWithProviders(<CardHarness confirmation={baseConfirmation} />);
        fireEvent.click(screen.getByRole("button", { name: "تأیید و اجرا" }));

        await waitFor(() => {
            expect(confirmPendingAction).toHaveBeenCalledWith("act-1");
        });
        await waitFor(() => {
            expect(screen.getByText(/اجرا شد/)).toBeInTheDocument();
        });
    });

    it("marks the card cancelled and never calls confirm on cancel", async () => {
        cancelPendingAction.mockResolvedValue({ cancelled: true });

        renderWithProviders(<CardHarness confirmation={baseConfirmation} />);
        fireEvent.click(screen.getByRole("button", { name: "لغو" }));

        await waitFor(() => {
            expect(cancelPendingAction).toHaveBeenCalledWith("act-1");
        });
        expect(confirmPendingAction).not.toHaveBeenCalled();
        await waitFor(() => {
            expect(screen.getByText(/لغو شد/)).toBeInTheDocument();
        });
    });

    it("shows an error state and appends an error message when approval fails", async () => {
        confirmPendingAction.mockRejectedValue(new Error("backend down"));

        renderWithProviders(<CardHarness confirmation={baseConfirmation} />);
        fireEvent.click(screen.getByRole("button", { name: "تأیید و اجرا" }));

        await waitFor(() => {
            expect(screen.getByText(/خطا در اجرا/)).toBeInTheDocument();
        });
        // The harness starts with 2 messages; the card appends the error note.
        await waitFor(() => {
            expect(screen.getByText("Error: backend down")).toBeInTheDocument();
        });
    });

    it("renders a neutral summary card for a non-pending status", () => {
        renderWithProviders(
            <PendingActionCard
                confirmation={{ ...baseConfirmation, status: "done" }}
                setMessages={vi.fn()}
                messageIndex={1}
                confIndex={0}
            />,
        );
        expect(screen.queryByText("نیاز به تأیید شما")).not.toBeInTheDocument();
        expect(screen.getByText(/create_note:/)).toBeInTheDocument();
    });
});
