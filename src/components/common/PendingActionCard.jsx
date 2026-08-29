import React, { useState } from "react";
import {
    Box,
    Button,
    HStack,
    Text,
    Spinner,
} from "@chakra-ui/react";
import { chatApi } from "../../utils/api/chatApi";

/**
 * Card shown for a mutating tool call that the backend parked for human
 * approval (chunk.type === "confirmation"). The user can approve the run or
 * cancel it; the outcome is echoed back onto the card.
 */
const PendingActionCard = ({
    confirmation,
    setMessages,
    messageIndex,
    confIndex,
}) => {
    const [busy, setBusy] = useState(false);
    const { actionId, tool, summary, status } = confirmation;

    const finalize = (newStatus, note) => {
        setMessages((prev) => {
            const next = [...prev];
            const msg = { ...next[messageIndex] };
            const confs = [...(msg.confirmations || [])];
            confs[confIndex] = { ...confs[confIndex], status: newStatus };
            next[messageIndex] = { ...msg, confirmations: confs };
            return next;
        });
        if (note) {
            setMessages((prev) => [
                ...prev,
                { role: "assistant", content: note },
            ]);
        }
    };

    const handleConfirm = async () => {
        setBusy(true);
        try {
            await chatApi.confirmPendingAction(actionId);
            finalize("done");
        } catch (error) {
            finalize("error", `Error: ${error.message}`);
        } finally {
            setBusy(false);
        }
    };

    const handleCancel = async () => {
        setBusy(true);
        try {
            await chatApi.cancelPendingAction(actionId);
            finalize("cancelled");
        } catch (error) {
            finalize("error", `Error: ${error.message}`);
        } finally {
            setBusy(false);
        }
    };

    if (status !== "pending") {
        const label =
            status === "done"
                ? "اجرا شد ✓"
                : status === "cancelled"
                  ? "لغو شد"
                  : "خطا در اجرا";
        return (
            <Box
                borderWidth="1px"
                borderRadius="md"
                px={3}
                py={2}
                fontSize="xs"
                color="overlay0"
            >
                {tool ? `${tool}: ` : ""}
                {label}
            </Box>
        );
    }

    return (
        <Box
            borderWidth="1px"
            borderRadius="md"
            px={3}
            py={2}
            fontSize="sm"
            width="100%"
        >
            <Text fontWeight="semibold" mb={1}>
                نیاز به تأیید شما
            </Text>
            {summary && (
                <Text fontSize="xs" color="overlay0" mb={2} whiteSpace="pre-wrap">
                    {summary}
                </Text>
            )}
            <HStack gap={2}>
                <Button
                    size="xs"
                    colorPalette="teal"
                    onClick={handleConfirm}
                    disabled={busy}
                >
                    {busy && <Spinner size="inherit" mr={1} />}تأیید و اجرا
                </Button>
                <Button
                    size="xs"
                    variant="outline"
                    onClick={handleCancel}
                    disabled={busy}
                >
                    لغو
                </Button>
            </HStack>
        </Box>
    );
};

export default PendingActionCard;
