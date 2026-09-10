import { Box, Text, InputGroup, Input, NativeSelect, VStack, HStack, Spinner } from "@chakra-ui/react";
import { Tooltip } from "@/components/ui/tooltip";
import { CheckCircleIcon } from "../common/icons";
import SecretField from "../common/SecretField";
import { applyLlmProviderDefaults } from "../../utils/aiProviders";

const modelSelectOptions = (current, options) => {
    const list = Array.isArray(options) ? options.filter(Boolean) : [];
    if (current && !list.includes(current)) {
        return [current, ...list];
    }
    return list;
};

const LlmTab = ({
    config,
    handleConfigChange,
    modelOptions,
    llmModelsLoading = false,
    urlStatus = { llm: false },
    llmProviders = [],
}) => {
    const selectedProvider = llmProviders.find(
        (item) => item.id === (config?.LLM_PROVIDER || "ollama"),
    );
    const primaryOptions = modelSelectOptions(config?.PRIMARY_MODEL, modelOptions);
    const secondaryOptions = modelSelectOptions(
        config?.SECONDARY_MODEL,
        modelOptions,
    );

    return (
        <VStack gap={4} align="stretch">
            <Box>
                <Text fontSize="md" fontWeight="bold">
                    مدل زبانی بزرگ (LLM)
                </Text>
                <Text fontSize="sm" color="overlay0">
                    ارائه‌دهنده مدل زبانی برای تولید گزارش‌های بالینی را
                    پیکربندی کنید.
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
                                    config?.LLM_BASE_URL,
                                )
                            }
                            className="input-style"
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
                                      { id: "groq", name: "Groq" },
                                      { id: "openrouter", name: "OpenRouter" },
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
                            "Ollama، Groq، OpenRouter، OpenAI و Anthropic پشتیبانی می‌شوند."}
                    </Text>
                </Box>

                <Box>
                    <Tooltip content="نشانی پایه نقطه پایانی API مدل زبانی سازگار با OpenAI/Ollama">
                        <Text fontSize="sm" mb="1" fontWeight={"bold"}>
                            نشانی پایه API (سازگار با OpenAI/Ollama)
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
                        />
                    </InputGroup>
                </Box>

                <Box>
                    <Tooltip content="کلید API برای احراز هویت سرویس سازگار با OpenAI/Ollama">
                        <Text fontSize="sm" mb="1" fontWeight={"bold"}>
                            کلید API
                        </Text>
                    </Tooltip>
                    <SecretField
                        storedValue={config?.LLM_API_KEY || ""}
                        onChange={(value) =>
                            handleConfigChange("LLM_API_KEY", value)
                        }
                        placeholder="sk-..."
                    />
                </Box>

                <Box>
                    <Tooltip content="مدل اصلی برای تولید پاسخ‌ها و یادداشت‌های بالینی">
                        <Text fontSize="sm" mb="1" fontWeight={"bold"}>
                            مدل اصلی
                        </Text>
                    </Tooltip>
                    {llmModelsLoading ? (
                        <HStack gap="2">
                            <Spinner size="sm" />
                            <Text fontSize="sm" color="overlay0">
                                در حال دریافت فهرست مدل‌ها...
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
                            >
                                {primaryOptions.length === 0 && (
                                    <option value="">انتخاب مدل</option>
                                )}
                                {primaryOptions.map((model) => (
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
                            مدل ثانویه
                        </Text>
                    </Tooltip>
                    {llmModelsLoading ? (
                        <HStack gap="2">
                            <Spinner size="sm" />
                            <Text fontSize="sm" color="overlay0">
                                در حال دریافت فهرست مدل‌ها...
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
                            >
                                {secondaryOptions.length === 0 && (
                                    <option value="">انتخاب مدل</option>
                                )}
                                {secondaryOptions.map((model) => (
                                    <option key={model} value={model}>
                                        {model}
                                    </option>
                                ))}
                            </NativeSelect.Field>
                            <NativeSelect.Indicator />
                        </NativeSelect.Root>
                    )}
                </Box>
            </VStack>
        </VStack>
    );
};

export default LlmTab;
