// Modal component to display disclaimer on first visit to landing page per session.
import { useState } from "react";
import {
    Button,
    Box,
    Text,
    VStack,
    HStack,
    Heading,
    Icon,
    Checkbox,
    Image,
    Dialog,
    Portal,
} from "@chakra-ui/react";
import { FaExclamationTriangle } from "react-icons/fa";

const DisclaimerModal = ({ isOpen, onClose }) => {
    const [agreed, setAgreed] = useState(false);

    const handleContinue = () => {
        if (!agreed) return;
        onClose();
    };

    return (
        <Dialog.Root
            open={isOpen}
            size='lg'
            closeOnInteractOutside={false}
            closeOnEscape={false}
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
                            <HStack>
                                <Image src="/logo.webp" alt="Phlox Logo" width="30px" />
                                <Heading as="h2" size="md" fontFamily="heading">اطلاعیه مهم</Heading>
                            </HStack>
                        </Dialog.Header>
                        {/* Warning alert */}
                        <Box
                            bg="surfaceMuted"
                            borderLeft="4px solid"
                            borderColor="secondaryButton"
                            width="90%"
                            marginLeft="5%"
                            p={3}
                            borderRadius="md"
                            mb={4}
                        >
                            <HStack align="start">
                                <Icon color="secondaryButton" mt={0.5} asChild><FaExclamationTriangle /></Icon>
                                <Text color="textPrimary" fontSize="sm" fontWeight="600">
                                    نرم‌افزار آزمایشی — استفاده با مسئولیت شما
                                </Text>
                            </HStack>
                        </Box>
                        <Dialog.Body
                            maxH="40vh"
                            overflowY="auto"
                            className="custom-scrollbar"
                        >
                            {/* Disclaimer content */}
                            <VStack align="stretch" gap={4}>
                                <Box>
                                    <Text
                                        color={"textPrimary"}
                                        fontSize="sm"
                                        fontWeight="600"
                                        mb={2}
                                    >
                                        فلوکس پروژه‌ای آزمایشی برای استفاده آموزشی و شخصی است؛
                                        استفاده از آن فقط با آگاهی از این موضوع مجاز است.
                                    </Text>
                                    <Text
                                        color={"textPrimary"}
                                        fontSize="sm"
                                        fontWeight="600"
                                    >
                                        این برنامه وسیله پزشکی تأییدشده نیست و نباید در محیط واقعی
                                        بالینی یا برای تصمیم‌گیری بالینی استفاده شود.
                                    </Text>
                                </Box>

                                <Box>
                                    <Text
                                        color={"textPrimary"}
                                        fontSize="sm"
                                        fontWeight="600"
                                        mb={2}
                                    >
                                        محدودیت‌های اصلی:
                                    </Text>
                                    <VStack align="stretch" gap={2}>
                                        <Text
                                            color={"textPrimary"}
                                            fontSize="sm"
                                        >
                                            <strong>کد آزمایشی:</strong> کد پروژه در حال توسعه است و ممکن است
                                            خطا و ناسازگاری داشته باشد.
                                        </Text>
                                        <Text
                                            color={"textPrimary"}
                                            fontSize="sm"
                                        >
                                            <strong>توهم‌های هوش مصنوعی:</strong> خروجی مدل زبانی، به‌ویژه مدل‌های کوچک،
                                            ممکن است غیرقابل اعتماد یا نادرست باشد و اطلاعات ظاهراً معقول اما غلط ارائه کند.
                                            محتوای تولیدشده را با منابع معتبر و قضاوت حرفه‌ای خود بررسی کنید.
                                        </Text>
                                        <Text
                                            color={"textPrimary"}
                                            fontSize="sm"
                                        >
                                            <strong>احراز هویت کاربر وجود ندارد:</strong>{" "}
                                            قرار دادن ساده این برنامه در اینترنت عمومی به‌شدت توصیه نمی‌شود. فلوکس
                                            کنترل دسترسی کاربر و پاک‌سازی کامل ورودی را فراهم نمی‌کند.
                                        </Text>
                                        <Text
                                            color={"textPrimary"}
                                            fontSize="sm"
                                        >
                                            <strong>با HIPAA/GDPR سازگار نیست:</strong>{" "}
                                            فلوکس اقدامات امنیتی و الزامات لازم برای نگهداری اطلاعات سلامت
                                            حفاظت‌شده در محیط‌های قانون‌گذاری‌شده را ندارد.
                                        </Text>
                                    </VStack>
                                </Box>

                                <Text color={"textPrimary"} fontSize="sm">
                                    فقط برای اهداف آموزشی و غیر بالینی و با مسئولیت خودتان استفاده کنید؛
                                    مگر آنکه اقدامات امنیتی قوی و اعتبارسنجی کامل انجام داده باشید.
                                </Text>

                                <Text color={"textSecondary"} fontSize="xs">
                                    این نرم‌افزار تحت مجوز MIT ارائه می‌شود.
                                </Text>
                            </VStack>
                        </Dialog.Body>
                        <Dialog.Footer>
                            <VStack w="100%" align="stretch" gap={3}>
                                <Checkbox.Root
                                    className="checkbox task-checkbox"
                                    onCheckedChange={({ checked }) => setAgreed(checked)}
                                    checked={agreed}
                                ><Checkbox.HiddenInput /><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Checkbox.Label>
                                    <Text
                                        color={"textPrimary"}
                                        fontSize="sm"
                                        css={{
                                            fontFamily: '"Roboto", sans-serif'
                                        }}
                                    >
                                        هشدارهای بالا را خوانده‌ام و درک می‌کنم. موافقم با مسئولیت خودم ادامه دهم.
                                    </Text>
                                </Checkbox.Label></Checkbox.Root>
                                <HStack justify="flex-end">
                                    <Button
                                        onClick={handleContinue}
                                        disabled={!agreed}
                                        size="md"
                                        borderRadius="2xl"
                                        className="green-button"
                                        css={{
                                            fontFamily: '"Space Grotesk", sans-serif',
                                            fontWeight: "600"
                                        }}
                                    >
                                        ادامه
                                    </Button>
                                </HStack>
                            </VStack>
                        </Dialog.Footer>
                    </Dialog.Content>
                </Dialog.Positioner>

            </Portal>
        </Dialog.Root>
    );
};

export default DisclaimerModal;
