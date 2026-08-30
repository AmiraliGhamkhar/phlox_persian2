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
    FaDatabase,
    FaPuzzlePiece,
} from "react-icons/fa";
import { useState, useEffect } from "react";

import ToolsSettingsTab from "./ToolsSettingsTab";
import LocalModelManager from "./LocalModelManager";
import WhisperTab from "./WhisperTab";
import LlmTab from "./LlmTab";
import RagTab from "./RagTab";
import { localModelApi } from "../../utils/api/localModelApi";
import { buildApiUrl, isTauri } from "../../utils/helpers/apiConfig";
import { universalFetch } from "../../utils/helpers/apiHelpers";
import { isRagEnabled } from "../../utils/helpers/featureFlags";

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
    embeddingModelOptions = [],
    handleReEmbed,
    llmProviders = [],
    asrProviders = [],
    embeddingProviders = [],
}) => {
    const [localStatus, setLocalStatus] = useState(null);
    const [isDocker, setIsDocker] = useState(false);

    // Determine if we're using local inference
    const isLocalInference = config?.LLM_PROVIDER === "local";

    const checkLocalStatus = async () => {
        try {
            const data = await localModelApi.checkLocalStatus();
            setLocalStatus(data);
        } catch (error) {
            console.error("Error checking local status:", error);
            setLocalStatus({
                available: false,
                reason: "Failed to check status",
            });
        }
    };

    const checkIfDocker = async () => {
        try {
            const response = await universalFetch(
                await buildApiUrl("/api/config/local/status"),
            );

            if (response.ok) {
                const data = await response.json();
                // Prefer explicit backend signal
                if (typeof data.is_docker === "boolean") {
                    setIsDocker(data.is_docker);
                } else {
                    // Fallback for older backend responses
                    setIsDocker(
                        !data.available && data.reason?.includes("Docker"),
                    );
                }
                return;
            }

            // Backward compatibility for older backend behavior
            if (response.status === 400) {
                const data = await response.json();
                if (data.detail?.includes("Tauri builds")) {
                    setIsDocker(true);
                }
            }
        } catch (error) {
            console.error("Error checking Docker status:", error);
        }
    };

    useEffect(() => {
        checkLocalStatus();
        checkIfDocker();
    }, []);

    const handleInferenceTypeChange = (isLocal) => {
        if (isLocal) {
            handleConfigChange("LLM_PROVIDER", "local");
            handleConfigChange("ASR_PROVIDER", "local");
            handleConfigChange("ASR_BASE_URL", "");
            handleConfigChange("WHISPER_BASE_URL", "");
            handleConfigChange("ASR_MODEL", "whisper-large-v3-turbo-q5_0");
            handleConfigChange("WHISPER_MODEL", "whisper-large-v3-turbo-q5_0");
        } else {
            handleConfigChange("LLM_PROVIDER", "openai");
            handleConfigChange("ASR_PROVIDER", "openai_compatible");
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
                        {/* Inference Type Selection - Desktop (Tauri) only and not in Docker */}
                        {isTauri() && !isDocker && (
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
                                                disabled={
                                                    !isTauri() &&
                                                    !localStatus?.available
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
                        )}

                        {isLocalInference ? (
                            <Tabs.Root
                                variant="enclosed"
                                defaultValue="0"
                            >
                                <Tabs.List>
                                    <Tooltip content="مدیریت مدل‌های زبانی و ASR محلی">
                                        <Tabs.Trigger
                                            className="tab-style"
                                            value="0"
                                        >
                                            <HStack>
                                                <FaDesktop />
                                                <Text>مدل‌ها</Text>
                                            </HStack>
                                        </Tabs.Trigger>
                                    </Tooltip>
                                    <Tooltip content="پیکربندی سرورهای ابزار خارجی">
                                        <Tabs.Trigger
                                            className="tab-style"
                                            value="1"
                                        >
                                            <HStack>
                                                <FaPuzzlePiece />
                                                <Text>ابزارها</Text>
                                            </HStack>
                                        </Tabs.Trigger>
                                    </Tooltip>
                                </Tabs.List>
                                <Tabs.Content
                                    className="floating-main"
                                    value="0"
                                >
                                    <LocalModelManager />
                                </Tabs.Content>
                                <Tabs.Content
                                    className="floating-main"
                                    value="1"
                                >
                                    <ToolsSettingsTab />
                                </Tabs.Content>
                            </Tabs.Root>
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
                                    {isRagEnabled() && (
                                        <Tooltip content="پیکربندی مدل بردارسازی پایگاه دانش">
                                            <Tabs.Trigger
                                                className="tab-style"
                                                value="2"
                                            >
                                                <HStack>
                                                    <FaDatabase />
                                                    <Text>پایگاه دانش</Text>
                                                </HStack>
                                            </Tabs.Trigger>
                                        </Tooltip>
                                    )}
                                    <Tooltip content="پیکربندی سرورهای ابزار خارجی">
                                        <Tabs.Trigger
                                            className="tab-style"
                                            value="3"
                                        >
                                            <HStack>
                                                <FaPuzzlePiece />
                                                <Text>ابزارها</Text>
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
                                {isRagEnabled() && (
                                    <Tabs.Content
                                        className="floating-main"
                                        value="2"
                                    >
                                        <RagTab
                                            config={config}
                                            embeddingModelOptions={
                                                embeddingModelOptions
                                            }
                                            llmModelsLoading={llmModelsLoading}
                                            handleReEmbed={handleReEmbed}
                                            handleConfigChange={handleConfigChange}
                                            embeddingProviders={embeddingProviders}
                                        />
                                    </Tabs.Content>
                                )}
                                <Tabs.Content
                                    className="floating-main"
                                    value="3"
                                >
                                    <ToolsSettingsTab />
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
