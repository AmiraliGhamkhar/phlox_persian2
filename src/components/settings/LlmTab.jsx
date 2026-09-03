import { Box, Text, InputGroup, Input, NativeSelect, VStack, HStack, Badge, Button, Alert, Spinner } from "@chakra-ui/react";
import { toaster } from "@/components/ui/toaster";
import { Tooltip } from "@/components/ui/tooltip";
import { CheckCircleIcon } from "../common/icons";
import { useState, useEffect } from "react";
import { chatApi } from "../../utils/api/chatApi";
import { applyLlmProviderDefaults } from "../../utils/aiProviders";

const LlmTab = ({
    config,
    handleConfigChange,
    modelOptions,
    llmModelsLoading = false,
    urlStatus = { llm: false },
    llmProviders = [],
}) => {
    const [isProbingVision, setIsProbingVision] = useState(false);
    const [visionProbeDetail, setVisionProbeDetail] = useState("");
    const [visionProbeStatus, setVisionProbeStatus] = useState("info");
    const [currentVisionCapability, setCurrentVisionCapability] =
        useState(null);
    const selectedProvider = llmProviders.find(
        (item) => item.id === (config?.LLM_PROVIDER || "ollama"),
    );

    const loadCurrentVisionCapability = async () => {
        try {
            const result = await chatApi.getCurrentVisionCapability();
            setCurrentVisionCapability(result || null);
        } catch (error) {
            console.error("Error loading current vision capability:", error);
            setCurrentVisionCapability(null);
        }
    };

    useEffect(() => {
        loadCurrentVisionCapability();
    }, [config?.LLM_PROVIDER, config?.LLM_BASE_URL, config?.PRIMARY_MODEL]);

    const handleProbeVisionCapability = async () => {
        setIsProbingVision(true);
        setVisionProbeDetail("");
        setVisionProbeStatus("info");

        try {
            const result = await chatApi.probeVisionCapability({
                model: config?.PRIMARY_MODEL || "",
                base_url: config?.LLM_BASE_URL || "",
            });

            const capable = Boolean(result?.vision_capable);
            const detail =
                result?.detail ||
                (capable
                    ? "Vision input accepted by endpoint/model."
                    : "Vision input was not accepted by endpoint/model.");

            if (!config?.DOCUMENT_IMAGE_PROCESSING_MODE) {
                handleConfigChange("DOCUMENT_IMAGE_PROCESSING_MODE", "auto");
            }

            setVisionProbeStatus(capable ? "success" : "warning");
            setVisionProbeDetail(detail);

            await loadCurrentVisionCapability();

            toaster.create({
                title: capable
                    ? "Vision capability detected"
                    : "Vision capability not detected",
                description: detail,
                status: capable ? "success" : "warning",
                duration: 4500,
            });
        } catch (error) {
            const detail =
                error?.message || "Failed to probe visual capability.";
            setVisionProbeStatus("error");
            setVisionProbeDetail(detail);
            setCurrentVisionCapability(null);

            toaster.create({
                title: "Vision capability probe failed",
                description: detail,
                type: "error",
                duration: 5000,
            });
        } finally {
            setIsProbingVision(false);
        }
    };

    return (
        <VStack gap={4} align="stretch">
            <Box>
                <Text fontSize="md" fontWeight="bold">
                    Large Language Model (LLM)
                </Text>
                <Text fontSize="sm" color="overlay0">
                    Configure the language model provider for generating
                    responses
                </Text>
            </Box>

            <VStack gap={3} align="stretch">
                <Box>
                    <Text fontSize="sm" mb="1" fontWeight={"bold"}>
                        ارائه‌دهنده مدل زبانی
                    </Text>
                    <NativeSelect.Root>
                        <NativeSelect.Field
                            size="sm"
                            value={config?.LLM_PROVIDER || "ollama"}
                            onChange={(event) =>
                                applyLlmProviderDefaults(
                                    event.target.value,
                                    handleConfigChange,
                                )
                            }
                            className="input-style"
                            data-testid="llm-provider-select"
                        >
                            {(llmProviders.length
                                ? llmProviders
                                : [
                                      { id: "ollama", name: "Ollama" },
                                      { id: "lmstudio", name: "LM Studio" },
                                      { id: "llamacpp", name: "llama.cpp server" },
                                      { id: "ninerouter", name: "9Router" },
                                      { id: "omniroute", name: "OmniRoute" },
                                      { id: "openai", name: "OpenAI" },
                                      { id: "anthropic", name: "Anthropic" },
                                      { id: "fireworks", name: "Fireworks AI" },
                                      {
                                          id: "openai_compatible",
                                          name: "Custom OpenAI-compatible",
                                      },
                                  ]
                            )
                                .filter((item) => item.id !== "local")
                                .map((item) => (
                                    <option key={item.id} value={item.id}>
                                        {item.name_fa || item.name}
                                    </option>
                                ))}
                        </NativeSelect.Field>
                        <NativeSelect.Indicator />
                    </NativeSelect.Root>
                    <Text fontSize="xs" color="overlay0" mt={1}>
                        {llmProviders.find((item) => item.id === config?.LLM_PROVIDER)
                            ?.help_fa ||
                            "Ollama، LM Studio، llama.cpp، 9Router، OmniRoute، OpenAI و Anthropic پشتیبانی می‌شوند."}
                    </Text>
                </Box>

                <Box>
                    <Tooltip content="نشانی پایه نقطه پایانی API مدل زبانی سازگار با OpenAI/Ollama">
                        <Text fontSize="sm" mb="1" fontWeight={"bold"}>
                            OpenAI/Ollama API Base URL
                        </Text>
                    </Tooltip>
                    <InputGroup
                        size="sm"
                        endElement={
                            urlStatus.llm ? (
                                <Tooltip content="اتصال موفق بود">
                                    <CheckCircleIcon color="successButton" />
                                </Tooltip>
                            ) : undefined
                        }
                    >
                        <Input
                            value={config?.LLM_BASE_URL || ""}
                            onChange={(e) =>
                                handleConfigChange(
                                    "LLM_BASE_URL",
                                    e.target.value,
                                )
                            }
                            placeholder={
                                selectedProvider?.placeholder_url ||
                                "https://api.example.com"
                            }
                            className="input-style"
                            data-testid="llm-base-url-input"
                        />
                    </InputGroup>
                </Box>

                <Box>
                    <Tooltip content="کلید API برای احراز هویت سرویس سازگار با OpenAI/Ollama">
                        <Text fontSize="sm" mb="1" fontWeight={"bold"}>
                            API Key
                        </Text>
                    </Tooltip>
                    <Input
                        size="sm"
                        type="password"
                        value={config?.LLM_API_KEY || ""}
                        onChange={(e) =>
                            handleConfigChange("LLM_API_KEY", e.target.value)
                        }
                        placeholder="sk-..."
                        className="input-style"
                        data-testid="llm-api-key-input"
                    />
                </Box>

                <Box>
                    <Tooltip content="مدل اصلی برای تولید پاسخ‌ها و یادداشت‌های بالینی">
                        <Text fontSize="sm" mb="1" fontWeight={"bold"}>
                            Primary Model
                        </Text>
                    </Tooltip>
                    {llmModelsLoading ? (
                        <HStack gap="2">
                            <Spinner size="sm" />
                            <Text fontSize="sm" color="overlay0">
                                Loading models...
                            </Text>
                        </HStack>
                    ) : (
                        <NativeSelect.Root>
                            <NativeSelect.Field
                                size="sm"
                                value={config?.PRIMARY_MODEL || ""}
                                onChange={(e) =>
                                    handleConfigChange(
                                        "PRIMARY_MODEL",
                                        e.target.value,
                                    )
                                }
                                placeholder="انتخاب مدل"
                                className="input-style"
                                data-testid="llm-primary-model-select"
                            >
                                {modelOptions.map((model) => (
                                    <option key={model} value={model}>
                                        {model}
                                    </option>
                                ))}
                            </NativeSelect.Field>
                            <NativeSelect.Indicator />
                        </NativeSelect.Root>
                    )}
                </Box>

                <Box>
                    <Tooltip content="مدل ثانویه برای کارهای با قابلیت متفاوت یا مقایسه">
                        <Text fontSize="sm" mb="1" fontWeight={"bold"}>
                            Secondary Model
                        </Text>
                    </Tooltip>
                    {llmModelsLoading ? (
                        <HStack gap="2">
                            <Spinner size="sm" />
                            <Text fontSize="sm" color="overlay0">
                                Loading models...
                            </Text>
                        </HStack>
                    ) : (
                        <NativeSelect.Root>
                            <NativeSelect.Field
                                size="sm"
                                value={config?.SECONDARY_MODEL || ""}
                                onChange={(e) =>
                                    handleConfigChange(
                                        "SECONDARY_MODEL",
                                        e.target.value,
                                    )
                                }
                                placeholder="انتخاب مدل"
                                className="input-style"
                                data-testid="llm-secondary-model-select"
                            >
                                {modelOptions.map((model) => (
                                    <option key={model} value={model}>
                                        {model}
                                    </option>
                                ))}
                            </NativeSelect.Field>
                            <NativeSelect.Indicator />
                        </NativeSelect.Root>
                    )}
                </Box>

                <Box>
                    <Tooltip content="نحوه پردازش PDF و تصویر را انتخاب کنید: مدل زبانی تصویری، جایگزین OCR یا انتخاب خودکار">
                        <Text fontSize="sm" mb="1" fontWeight={"bold"}>
                            Document/Image Processing Mode
                        </Text>
                    </Tooltip>
                    <NativeSelect.Root>
                        <NativeSelect.Field
                            size="sm"
                            value={
                                config?.DOCUMENT_IMAGE_PROCESSING_MODE || "auto"
                            }
                            onChange={(e) =>
                                handleConfigChange(
                                    "DOCUMENT_IMAGE_PROCESSING_MODE",
                                    e.target.value,
                                )
                            }
                            className="input-style"
                            data-testid="llm-processing-mode-select"
                        >
                            <option value="auto">
                                Auto (prefer visual if available)
                            </option>
                            <option value="vision">فقط تصویری</option>
                            <option value="ocr">فقط OCR</option>
                        </NativeSelect.Field>
                        <NativeSelect.Indicator />
                    </NativeSelect.Root>
                    <Text fontSize="xs" color="overlay0" mt="1">
                        Auto uses visual processing when vision capability is
                        detected; otherwise it falls back to OCR-compatible
                        endpoints.
                    </Text>
                </Box>

                <Box>
                    <Tooltip content="ارسال یک تصویر آزمایشی کوچک برای بررسی پشتیبانی نقطه پایانی یا مدل انتخاب‌شده از تصویر">
                        <Text fontSize="sm" mb="1" fontWeight={"bold"}>
                            Vision Capability Probe
                        </Text>
                    </Tooltip>

                    <HStack gap={3} mb={2}>
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={handleProbeVisionCapability}
                            loading={isProbingVision}
                            data-testid="llm-vision-probe-button"
                        >
                            Test Vision Support
                        </Button>
                        <Badge
                            colorPalette={
                                currentVisionCapability?.vision_capable
                                    ? "green"
                                    : currentVisionCapability
                                      ? "red"
                                      : "gray"
                            }
                        >
                            {currentVisionCapability
                                ? currentVisionCapability.vision_capable
                                    ? "دارای قابلیت تصویری"
                                    : "بدون قابلیت تصویری"
                                    : "Unknown"}
                        </Badge>
                    </HStack>
                    {currentVisionCapability ? (
                        <Text fontSize="xs" color="overlay0" mb={2}>
                            Source:{" "}
                            {currentVisionCapability.source || "cache"}
                            {currentVisionCapability.probed_at
                                ? ` • Probed: ${currentVisionCapability.probed_at}`
                                : ""}
                        </Text>
                    ) : null}

                    {visionProbeDetail ? (
                        <Alert.Root
                            status={visionProbeStatus}
                            borderRadius="sm"
                            py={2}
                        >
                            <Alert.Indicator />
                            <Text fontSize="xs" whiteSpace="pre-wrap">
                                {visionProbeDetail}
                            </Text>
                        </Alert.Root>
                    ) : null}
                </Box>
            </VStack>
        </VStack>
    );
};

export default LlmTab;
