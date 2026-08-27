import { Button, HStack, Heading, Text, Dialog, Portal } from "@chakra-ui/react";

const formatDate = (iso) => {
    if (!iso) return "";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("fa-IR");
};

const ScribeConsentModal = ({
    isOpen,
    onClose,
    onConsent,
    onDecline,
    hasDeclined = false,
    declinedDate = null,
    patientName = "",
}) => {
    const name = patientName || "این بیمار";
    return (
        <Dialog.Root
            open={isOpen}
            size='md'
            closeOnInteractOutside={false}
            onOpenChange={e => {
                if (!e.open) {
                    onClose();
                }
            }}
        >
            <Portal>

                <Dialog.Backdrop />
                <Dialog.Positioner>
                    <Dialog.Content className="modal-style">
                        <Dialog.Header>
                            <Heading as="h2" size="md" fontFamily="heading">
                                {hasDeclined
                                    ? "رضایت قبلاً رد شده است"
                                    : "رضایت برای دستیار محیطی"}
                            </Heading>
                        </Dialog.Header>
                        <Dialog.CloseTrigger />
                        <Dialog.Body>
                            {hasDeclined ? (
                                <Text dir="auto">
                                    {name} قبلاً با ثبت محیطی صدا موافقت نکرده است
                                    {declinedDate ? ` در تاریخ ${formatDate(declinedDate)}` : ""}.
                                    آیا می‌خواهید پیش از ضبط دوباره درخواست رضایت کنید؟
                                </Text>
                            ) : (
                                <Text dir="auto">
                                    {name} هنوز با ثبت محیطی صدا موافقت نکرده است. حالت محیطی
                                    مشاوره را ضبط می‌کند — لطفاً پیش از شروع ضبط، رضایت بیمار
                                    را تأیید کنید.
                                </Text>
                            )}
                        </Dialog.Body>
                        <Dialog.Footer>
                            <HStack justify="flex-end" width="100%">
                                {hasDeclined ? (
                                    <Button
                                        className="red-button"
                                        mr={3}
                                        onClick={onClose}
                                    >
                                        انصراف
                                    </Button>
                                ) : (
                                    <Button
                                        className="red-button"
                                        mr={3}
                                        onClick={onDecline}
                                    >
                                        Decline
                                    </Button>
                                )}
                                <Button className="green-button" onClick={onConsent}>
                                    {hasDeclined ? "درخواست دوباره رضایت" : "موافقت"}
                                </Button>
                            </HStack>
                        </Dialog.Footer>
                    </Dialog.Content>
                </Dialog.Positioner>

            </Portal>
        </Dialog.Root>
    );
};

export default ScribeConsentModal;
