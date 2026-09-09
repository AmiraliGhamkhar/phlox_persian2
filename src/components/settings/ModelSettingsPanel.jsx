import { Box, Flex, IconButton, Text, Collapsible, VStack, Tabs, HStack, Button } from "@chakra-ui/react";
import { Tooltip } from "@/components/ui/tooltip";
import {
    ChevronRightIcon,
    ChevronDownIcon,
} from "../common/icons";
import {
    FaCog,
    FaDesktop,
    FaCloud,
    FaMicrophone,
    FaBrain,
} from "react-icons/fa";

import LocalModelManager from "./LocalModelManager";
import WhisperTab from "./WhisperTab";
import LlmTab from "./LlmTab";
import {
    applyAsrProviderDefaults,
    applyLlmProviderDefaults,
} from "../../utils/aiProviders";

const ModelSettingsPanel = ({
    isCollapsed,
    setIsCollapsed,
    config,
    handleConfigChange,
    modelOptions,
    whisperModelOptions = [],
    whisperModelListAvailable = false,
    whisperModelsLoading = false,
    llmModelsLoading = false,
    urlStatus = { whisper: false, llm: false },
    llmProviders = [],
    asrProviders = [],
}) => {
    // Determine if we're using local inference
    const isLocalInference = config?.LLM_PROVIDER === "local";

    const handleInferenceTypeChange = (isLocal) => {
        if (isLocal) {
            handleConfigChange("LLM_PROVIDER", "local");
            handleConfigChange("ASR_PROVIDER", "local");
            handleConfigChange("ASR_BASE_URL", "");
            handleConfigChange("WHISPER_BASE_URL", "");
            handleConfigChange("ASR_MODEL", "whisper-large-v3-turbo-q6_k");
            handleConfigChange("WHISPER_MODEL", "whisper-large-v3-turbo-q6_k");
        } else {
            // Stamp cloud defaults so an empty OpenAI URL cannot fall through
            // to the historical Ollama localhost:11434 resolver, and leftover
            // local GGUF / Whisper ids are not sent to a remote API.
            applyLlmProviderDefaults("openai", handleConfigChange);
            applyAsrProviderDefaults("openai_compatible", handleConfigChange);
        }
    };

    return (
        <Box className="panels-bg" p="4" borderRadius="sm">
            <Flex align="center" justify="space-between">
                <Flex align="center">
                    <IconButton
                        onClick={() => setIsCollapsed(!isCollapsed)}
                        aria-label="باز و بسته کردن بخش"
                        variant="outline"
                        size="sm"
                        mr="2"
                        className="collapse-toggle"
                    >
                        {isCollapsed ? (
                            <ChevronRightIcon />
                        ) : (
                            <ChevronDownIcon />
                        )}
                    </IconButton>
                    <FaCog size="1.2em" style={{ marginRight: "5px" }} />
                    <Text as="h3">تنظیمات مدل</Text>
                </Flex>
            </Flex>
            <Collapsible.Root open={!isCollapsed}>
                <Collapsible.Content>
                    <VStack gap={4} align="stretch" mt={4}>
                        {/* Inference Type Selection — local models run on
                            desktop and in Docker; the manager below reports
                            availability when the runtime has no binaries. */}
                        <Box>
                            <Tooltip content="انتخاب اجرای محلی مدل‌ها یا اتصال به سرویس‌های API راه‌دور">
                                <Text
                                    fontSize="md"
                                    fontWeight="bold"
                                    mb="3"
                                >
                                    Inference Type
                                </Text>
                            </Tooltip>
                            <Flex
                                className="mode-selector"
                                alignItems="center"
                                p={1}
                                width="100%"
                            >
                                <Box
                                    className="mode-selector-indicator"
                                    left={
                                        isLocalInference
                                            ? "2px"
                                            : "calc(50% - 2px)"
                                    }
                                />
                                <Flex
                                    width="full"
                                    position="relative"
                                    zIndex={1}
                                >
                                    <Tooltip content="اجرای مستقیم مدل‌ها روی دستگاه با موتورهای استنتاج داخلی">
                                        <Button
                                            className={`mode-selector-button ${isLocalInference ? "active" : ""}`}
                                            onClick={() =>
                                                handleInferenceTypeChange(
                                                    true,
                                                )
                                            }
                                        >
                                            <FaDesktop />
                                            Local
                                        </Button>
                                    </Tooltip>
                                    <Tooltip content="اتصال به APIهای خارجی سازگار با OpenAI/Ollama">
                                        <Button
                                            className={`mode-selector-button ${!isLocalInference ? "active" : ""}`}
                                            onClick={() =>
                                                handleInferenceTypeChange(
                                                    false,
                                                )
                                            }
                                        >
                                            <FaCloud />
                                            Remote
                                        </Button>
                                    </Tooltip>
                                </Flex>
                            </Flex>
                        </Box>

                        {isLocalInference ? (
                            <LocalModelManager />
                        ) : (
                            <Tabs.Root
                                variant="enclosed"
                                defaultValue="0"
                            >
                                <Tabs.List>
                                    <Tooltip content="پیکربندی سرویس تشخیص گفتار">
                                        <Tabs.Trigger
                                            className="tab-style"
                                            value="0"
                                        >
                                            <HStack>
                                                <FaMicrophone />
                                                <Text>تشخیص گفتار</Text>
                                            </HStack>
                                        </Tabs.Trigger>
                                    </Tooltip>
                                    <Tooltip content="پیکربندی ارائه‌دهنده مدل زبانی">
                                        <Tabs.Trigger
                                            className="tab-style"
                                            value="1"
                                        >
                                            <HStack>
                                                <FaBrain />
                                                <Text>مدل زبانی</Text>
                                            </HStack>
                                        </Tabs.Trigger>
                                    </Tooltip>
                                </Tabs.List>
                                <Tabs.Content
                                    className="floating-main"
                                    value="0"
                                >
                                    <WhisperTab
                                        config={config}
                                        handleConfigChange={handleConfigChange}
                                        whisperModelOptions={
                                            whisperModelOptions
                                        }
                                        whisperModelListAvailable={
                                            whisperModelListAvailable
                                        }
                                        whisperModelsLoading={
                                            whisperModelsLoading
                                        }
                                        urlStatus={urlStatus}
                                        asrProviders={asrProviders}
                                    />
                                </Tabs.Content>
                                <Tabs.Content
                                    className="floating-main"
                                    value="1"
                                >
                                    <LlmTab
                                        config={config}
                                        handleConfigChange={handleConfigChange}
                                        modelOptions={modelOptions}
                                        llmModelsLoading={llmModelsLoading}
                                        urlStatus={urlStatus}
                                        llmProviders={llmProviders}
                                    />
                                </Tabs.Content>
                            </Tabs.Root>
                        )}
                    </VStack>
                </Collapsible.Content>
            </Collapsible.Root>
        </Box>
    );
};

export default ModelSettingsPanel;
