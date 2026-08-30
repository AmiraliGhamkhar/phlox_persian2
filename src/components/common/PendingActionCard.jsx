import React, { useState } from "react";
import {
    Box,
    Button,
    HStack,
    Text,
    Spinner,
} from "@chakra-ui/react";
import { chatApi } from "../../utils/api/chatApi";
import { normalizeChatArtifacts } from "../../utils/chat/artifacts";

/**
 * Card shown for a mutating tool call that the backend parked for human
 * approval (chunk.type === "confirmation"). The user can approve the run or
 * cancel it; the outcome (including the tool result) is echoed back onto
 * the card and into the chat transcript.
 */
const PendingActionCard = ({
    confirmation,
    setMessages,
    messageIndex,
    confIndex,
}) => {
    const [busy, setBusy] = useState(false);
    const { actionId, tool, summary, status, result } = confirmation;

    const patchConfirmation = (updates, extraMessage, extraArtifacts) => {
        setMessages((prev) => {
            const next = [...prev];
            const msg = { ...next[messageIndex] };
            const confs = [...(msg.confirmations || [])];
            confs[confIndex] = { ...confs[confIndex], ...updates };
            const artifacts = extraArtifacts?.length
                ? [...(msg.artifacts || []), ...extraArtifacts]
                : msg.artifacts;
            next[messageIndex] = { ...msg, confirmations: confs, artifacts };
            if (extraMessage) {
                next.push({ role: "assistant", content: extraMessage });
            }
            return next;
        });
    };

    const handleConfirm = async () => {
        setBusy(true);
        try {
            const data = await chatApi.confirmPendingAction(actionId);
            const resultText =
                typeof data?.result === "string" && data.result.trim()
                    ? data.result.trim()
                    : "";
            const artifacts = normalizeChatArtifacts(data?.artifacts || []);
            patchConfirmation(
                { status: "done", result: resultText },
                resultText || null,
                artifacts,
            );
        } catch (error) {
            patchConfirmation(
                { status: "error" },
                `Error: ${error.message}`,
            );
        } finally {
            setBusy(false);
        }
    };

    const handleCancel = async () => {
        setBusy(true);
        try {
            await chatApi.cancelPendingAction(actionId);
            patchConfirmation({ status: "cancelled" });
        } catch (error) {
            patchConfirmation(
                { status: "error" },
                `Error: ${error.message}`,
            );
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
                width="100%"
            >
                <Text>
                    {tool ? `${tool}: ` : ""}
                    {label}
                </Text>
                {status === "done" && result && (
                    <Text mt={1} whiteSpace="pre-wrap">
                        {result}
                    </Text>
                )}
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
