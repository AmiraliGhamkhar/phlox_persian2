import { Button, HStack, Heading, Textarea, Box, Text, VStack, Dialog, Portal } from "@chakra-ui/react";

const NewTemplateFromExampleModal = ({
    isOpen,
    onClose,
    onCreate,
    exampleNote,
    setExampleNote,
    isLoading,
}) => {
    return (
        <Dialog.Root open={isOpen} size='lg' onOpenChange={e => {
            if (!e.open) {
                onClose();
            }
        }}>
            <Portal>

                <Dialog.Backdrop />
                <Dialog.Positioner>
                    <Dialog.Content className="modal-style">
                        <Dialog.Header><Heading as="h2" size="md" fontFamily="heading">قالب جدید از روی نمونه</Heading></Dialog.Header>
                        <Dialog.CloseTrigger />
                        <Dialog.Body
                            maxH="50vh"
                            overflowY="auto"
                            className="custom-scrollbar"
                        >
                            <VStack gap={4} align="stretch">
                                {/* Info box */}
                                <Box
                                    bg="surfaceMuted"
                                    borderLeft="4px solid"
                                    borderColor="accent"
                                    p={4}
                                    borderRadius="md"
                                >
                                    <VStack align="start" gap={2}>
                                        <Text
                                            color="textPrimary"
                                            fontWeight="600"
                                            fontSize="sm"
                                        >
                                            ساخت قالب از یک یادداشت موجود
                                        </Text>
                                        <Text
                                            color="textSecondary"
                                            fontSize="sm"
                                        >
                                            یک یادداشت بالینی نمونه را در زیر جای‌گذاری کنید.
                                            هوش مصنوعی ساختار آن را تحلیل می‌کند و به‌صورت
                                            خودکار قالبی با فیلدهای متناظر می‌سازد.
                                        </Text>
                                    </VStack>
                                </Box>

                                {/* Tips */}
                                <Box px={2}>
                                    <Text
                                        color="textPrimary"
                                        fontSize="xs"
                                        fontWeight="600"
                                        mb={2}
                                    >
                                        نکات برای بهترین نتیجه:
                                    </Text>
                                    <VStack align="start" gap={1} pl={2}>
                                        <Text
                                            color="textSecondary"
                                            fontSize="sm"
                                        >
                                            • یک یادداشت کامل و منظم را به‌عنوان نمونه انتخاب کنید
                                        </Text>
                                        <Text
                                            color="textSecondary"
                                            fontSize="sm"
                                        >
                                            • بخش‌های معمول مانند ذهنی، عینی، ارزیابی و برنامه را وارد کنید
                                        </Text>
                                        <Text
                                            color="textSecondary"
                                            fontSize="sm"
                                        >
                                            • هوش مصنوعی نام فیلدها و ارتباط میان آن‌ها را شناسایی می‌کند
                                        </Text>
                                    </VStack>
                                </Box>

                                {/* Textarea */}
                                <Textarea
                                    placeholder={`یادداشت نمونه خود را اینجا جای‌گذاری کنید...

        نمونه:
        ذهنی: بیمار با ... مراجعه کرده است
        عینی: علائم حیاتی طبیعی است و معاینه نشان می‌دهد...
        ارزیابی: تشخیص محتمل ...
        برنامه: ۱. تجویز دارو ۲. پیگیری طی ۲ هفته`}
                                    value={exampleNote}
                                    onChange={(e) => setExampleNote(e.target.value)}
                                    className="input-style"
                                    minH="200px"
                                    resize="vertical"
                                />
                            </VStack>
                        </Dialog.Body>
                        <Dialog.Footer>
                            <HStack justify="flex-end" width="100%">
                                <Button
                                    onClick={onClose}
                                    size="md"
                                    borderRadius="2xl"
                                    className="switch-mode"
                                    css={{
                                        fontFamily: '"Space Grotesk", sans-serif',
                                        fontWeight: "600"
                                    }}
                                    mr={3}
                                >
                                    انصراف
                                </Button>
                                <Button
                                    onClick={onCreate}
                                    loading={isLoading}
                                    loadingText="در حال ایجاد..."
                                    size="md"
                                    borderRadius="2xl"
                                    className="green-button"
                                    css={{
                                        fontFamily: '"Space Grotesk", sans-serif',
                                        fontWeight: "600"
                                    }}
                                >
ساخت قالب
                                </Button>
                            </HStack>
                        </Dialog.Footer>
                    </Dialog.Content>
                </Dialog.Positioner>

            </Portal>
        </Dialog.Root>
    );
};

export default NewTemplateFromExampleModal;
