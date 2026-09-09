import { Box, Text, InputGroup, Input, NativeSelect, VStack, HStack, Spinner } from "@chakra-ui/react";
import { Tooltip } from "@/components/ui/tooltip";
import { CheckCircleIcon } from "../common/icons";
import { applyLlmProviderDefaults } from "../../utils/aiProviders";

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

    return (
        <VStack gap={4} align="stretch">
            <Box>
                <Text fontSize="md" fontWeight="bold">
                    Large Language Model (LLM)
                </Text>
                <Text fontSize="sm" color="overlay0">
                    Configure the language model provider for generating
                    clinical reports
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
            </VStack>
        </VStack>
    );
};

export default LlmTab;
