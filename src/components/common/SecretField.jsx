import { useEffect, useRef, useState } from "react";
import { Button, HStack, Input } from "@chakra-ui/react";
import { FaEraser } from "react-icons/fa";
import { Tooltip } from "@/components/ui/tooltip";

const MASK_BULLET = "•";

/**
 * Input for API keys that the server returns masked (e.g. "abc••••wxyz").
 *
 * The server refuses to overwrite a stored secret with a value containing
 * mask bullets, so letting users edit the masked string would silently drop
 * their changes. This field never exposes the masked value for editing: it
 * starts empty, shows the masked value in the placeholder, and treats any
 * typing as a brand-new key. Clearing the input reverts to "keep stored
 * key"; removing the stored key is an explicit button.
 */
const SecretField = ({
    storedValue,
    onChange,
    placeholder,
    size = "sm",
    clearLabel = "پاک کردن کلید ذخیره‌شده",
}) => {
    // null = "no change typed yet" (keep whatever is stored).
    const [draft, setDraft] = useState(null);
    // Last value this field propagated upward; a storedValue change that we
    // caused ourselves must not reset the draft while the user is typing.
    const lastEmittedRef = useRef(storedValue);

    // A genuinely new value arriving from the server resets the draft.
    useEffect(() => {
        if (storedValue !== lastEmittedRef.current) {
            lastEmittedRef.current = storedValue;
            setDraft(null);
        }
    }, [storedValue]);

    const masked = typeof storedValue === "string" ? storedValue : "";
    const hasStoredKey = masked.length > 0 && masked !== MASK_BULLET;

    const handleInput = (event) => {
        const value = event.target.value;
        lastEmittedRef.current = value === "" ? masked : value;
        if (value === "") {
            // Reverting to the masked value tells the server "keep the key".
            setDraft(null);
            onChange(masked);
            return;
        }
        setDraft(value);
        onChange(value);
    };

    return (
        <HStack gap={2}>
            <Input
                size={size}
                type="password"
                dir="ltr"
                data-ltr="true"
                value={draft ?? ""}
                onChange={handleInput}
                placeholder={
                    masked
                        ? `${masked} — برای تغییر، کلید جدید را وارد کنید`
                        : placeholder || "کلید API"
                }
                className="input-style"
                flex={1}
            />
            {hasStoredKey && (
                <Tooltip content={clearLabel}>
                    <Button
                        size={size}
                        variant="ghost"
                        onClick={() => {
                            setDraft("");
                            lastEmittedRef.current = "";
                            onChange("");
                        }}
                        aria-label={clearLabel}
                    >
                        <FaEraser />
                    </Button>
                </Tooltip>
            )}
        </HStack>
    );
};

export default SecretField;
