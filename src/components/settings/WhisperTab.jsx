import {
    Box,
    HStack,
    Input,
    InputGroup,
    NativeSelect,
    Spinner,
    Text,
    VStack,
} from "@chakra-ui/react";
import { Tooltip } from "@/components/ui/tooltip";
import { CheckCircleIcon } from "../common/icons";

const WhisperTab = ({
    config,
    handleConfigChange,
    whisperModelOptions = [],
    whisperModelListAvailable = false,
    whisperModelsLoading = false,
    urlStatus = { whisper: false },
}) => {
    const provider = config?.ASR_PROVIDER || "openai_compatible";
    const isExternalProvider = provider !== "local";
    const modelValue = config?.ASR_MODEL || config?.WHISPER_MODEL || "";

    const updateModel = (value) => {
        handleConfigChange("ASR_MODEL", value);
        handleConfigChange("WHISPER_MODEL", value);
    };

    const updateKey = (value) => {
        handleConfigChange("ASR_KEY", value);
        handleConfigChange("WHISPER_KEY", value);
    };

    return (
        <VStack gap={4} align="stretch" dir="rtl">
            <Box>
                <Text fontSize="md" fontWeight="bold">
                    ASR؛ تشخیص خودکار گفتار
                </Text>
                <Text fontSize="sm" color="overlay0">
                    سرویس پیاده‌سازی صدای ضبط‌شده را انتخاب و پیکربندی کنید.
                </Text>
            </Box>

            <VStack gap={3} align="stretch">
                <Box>
                    <Text fontSize="sm" mb="1" fontWeight="bold">
                        ارائه‌دهنده ASR
                    </Text>
                    <NativeSelect.Root>
                        <NativeSelect.Field
                            size="sm"
                            value={provider}
                            onChange={(event) =>
                                handleConfigChange("ASR_PROVIDER", event.target.value)
                            }
                            className="input-style"
                        >
                            <option value="local">مدل محلی؛ Whisper.cpp یا Shenava</option>
                            <option value="openai_compatible">سرویس سازگار با OpenAI</option>
                            <option value="speechmatics">Speechmatics؛ بلادرنگ</option>
                        </NativeSelect.Field>
                        <NativeSelect.Indicator />
                    </NativeSelect.Root>
                    <Text fontSize="xs" color="overlay0" mt={1}>
                        ارائه‌دهنده، مدل و زبان ASR مستقل از مدل زبانی انتخاب می‌شوند.
                    </Text>
                </Box>

                <Box>
                    <Text fontSize="sm" mb="1" fontWeight="bold">
                        زبان گفتار
                    </Text>
                    <NativeSelect.Root>
                        <NativeSelect.Field
                            size="sm"
                            value={config?.ASR_LANGUAGE || config?.WHISPER_LANGUAGE || "auto"}
                            onChange={(event) => {
                                handleConfigChange("ASR_LANGUAGE", event.target.value);
                                handleConfigChange("WHISPER_LANGUAGE", event.target.value);
                            }}
                            className="input-style"
                        >
                            <option value="auto">تشخیص خودکار؛ فارسی و انگلیسی ترکیبی</option>
                            <option value="fa">فارسی</option>
                            <option value="en">انگلیسی</option>
                        </NativeSelect.Field>
                        <NativeSelect.Indicator />
                    </NativeSelect.Root>
                </Box>

                {provider === "openai_compatible" && (
                    <Box>
                        <Tooltip content="نشانی پایه سرویس سازگار با OpenAI را وارد کنید.">
                            <Text fontSize="sm" mb="1" fontWeight="bold">
                                نشانی پایه سرویس ASR
                            </Text>
                        </Tooltip>
                        <InputGroup
                            size="sm"
                            endElement={
                                urlStatus.whisper ? (
                                    <Tooltip content="ارتباط با سرویس برقرار است.">
                                        <CheckCircleIcon color="successButton" />
                                    </Tooltip>
                                ) : undefined
                            }
                        >
                            <Input
                                type="url"
                                data-ltr="true"
                                dir="ltr"
                                value={config?.ASR_BASE_URL || config?.WHISPER_BASE_URL || ""}
                                onChange={(event) => {
                                    handleConfigChange("ASR_BASE_URL", event.target.value);
                                    handleConfigChange("WHISPER_BASE_URL", event.target.value);
                                }}
                                placeholder="https://api.openai.com"
                                className="input-style"
                            />
                        </InputGroup>
                    </Box>
                )}

                {provider === "speechmatics" && (
                    <Text fontSize="xs" color="overlay0">
                        Speechmatics از نشانی منطقه‌ای پیش‌فرض استفاده می‌کند. در صورت نیاز می‌توانید نشانی سفارشی را در تنظیمات پیشرفته وارد کنید.
                    </Text>
                )}

                <Box>
                    <Tooltip content="مدلی را انتخاب کنید که برای پیاده‌سازی گفتار استفاده می‌شود.">
                        <Text fontSize="sm" mb="1" fontWeight="bold">
                            مدل ASR
                        </Text>
                    </Tooltip>

                    {provider === "speechmatics" ? (
                        <NativeSelect.Root>
                            <NativeSelect.Field
                                size="sm"
                                value={modelValue || "enhanced"}
                                onChange={(event) => updateModel(event.target.value)}
                                className="input-style"
                            >
                                <option value="enhanced">حالت پیشرفته؛ دقت بالاتر</option>
                                <option value="standard">حالت استاندارد؛ سرعت بالاتر</option>
                            </NativeSelect.Field>
                            <NativeSelect.Indicator />
                        </NativeSelect.Root>
                    ) : whisperModelsLoading ? (
                        <HStack gap="2">
                            <Spinner size="sm" />
                            <Text fontSize="sm" color="overlay0">
                                در حال دریافت فهرست مدل‌ها…
                            </Text>
                        </HStack>
                    ) : whisperModelListAvailable && whisperModelOptions.length > 0 ? (
                        <NativeSelect.Root>
                            <NativeSelect.Field
                                size="sm"
                                value={modelValue}
                                onChange={(event) => updateModel(event.target.value)}
                                className="input-style"
                            >
                                <option value="">انتخاب مدل ASR</option>
                                {whisperModelOptions.map((model) => (
                                    <option key={model} value={model}>
                                        {model}
                                    </option>
                                ))}
                            </NativeSelect.Field>
                            <NativeSelect.Indicator />
                        </NativeSelect.Root>
                    ) : (
                        <Input
                            size="sm"
                            dir="ltr"
                            data-ltr="true"
                            placeholder={
                                provider === "local"
                                    ? "whisper-large-v3-turbo-q5_0"
                                    : "whisper-1"
                            }
                            value={modelValue}
                            onChange={(event) => updateModel(event.target.value)}
                            className="input-style"
                        />
                    )}
                </Box>

                {isExternalProvider && (
                    <Box>
                        <Tooltip content="کلید در پیکربندی رمزگذاری‌شده ذخیره و هنگام نمایش پوشانده می‌شود.">
                            <Text fontSize="sm" mb="1" fontWeight="bold">
                                کلید API
                            </Text>
                        </Tooltip>
                        <Input
                            size="sm"
                            type="password"
                            dir="ltr"
                            data-ltr="true"
                            value={config?.ASR_KEY || config?.WHISPER_KEY || ""}
                            onChange={(event) => updateKey(event.target.value)}
                            placeholder={
                                provider === "speechmatics"
                                    ? "کلید Speechmatics"
                                    : "کلید API، در صورت نیاز"
                            }
                            className="input-style"
                        />
                    </Box>
                )}
            </VStack>
        </VStack>
    );
};

export default WhisperTab;
