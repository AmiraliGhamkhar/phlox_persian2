import {
    Box,
    Text,
    VStack,
    Center,
    Spinner,
    Input,
} from "@chakra-ui/react";
import { toaster } from "@/components/ui/toaster";
import { useState, useEffect, useCallback } from "react";
import { settingsService } from "../utils/settings/settingsUtils";
import { settingsApi } from "../utils/api/settingsApi";
import ModelSettingsPanel from "../components/settings/ModelSettingsPanel";
import { localModelApi } from "../utils/api/localModelApi";
import { isTauri } from "../utils/helpers/apiConfig";
import { useDebounce } from "../utils/hooks/useDebounce";
import { useAutosave } from "../utils/hooks/useAutosave";
import { useWorkspace } from "../utils/context/workspaceContext";

const Settings = () => {
    const { clinicianName, setClinicianName, refreshStatus } = useWorkspace();
    const [name, setName] = useState(clinicianName || "");
    const [config, setConfig] = useState(null);
    const [coreLoading, setCoreLoading] = useState(true);
    const [showSpinner, setShowSpinner] = useState(false);
    const [llmModelsLoading, setLlmModelsLoading] = useState(false);
    const [whisperModelsLoading, setWhisperModelsLoading] = useState(false);
    const [modelOptions, setModelOptions] = useState([]);
    const [whisperModelOptions, setWhisperModelOptions] = useState([]);
    const [whisperModelListAvailable, setWhisperModelListAvailable] =
        useState(false);
    const [llmProviders, setLlmProviders] = useState([]);
    const [asrProviders, setAsrProviders] = useState([]);
    const [urlStatus, setUrlStatus] = useState({
        whisper: false,
        llm: false,
    });
    const [collapseStates, setCollapseStates] = useState({
        modelSettings: false,
    });

    useEffect(() => {
        if (clinicianName && !name) setName(clinicianName);
    }, [clinicianName, name]);

    const fetchCoreSettings = useCallback(async () => {
        try {
            setCoreLoading(true);
            const configData = await settingsApi.fetchConfig();
            setConfig(configData);
            try {
                const catalog = await settingsApi.fetchProviders();
                setLlmProviders(catalog?.llm || []);
                setAsrProviders(catalog?.asr || []);
            } catch (error) {
                console.error("Error loading AI provider catalog:", error);
            }
            const userSettings = await settingsApi.fetchUserSettings();
            if (userSettings?.name) setName(userSettings.name);
        } catch (error) {
            console.error("Error loading settings:", error);
            toaster.create({
                title: "Error loading settings",
                description: error.message,
                type: "error",
                duration: 3000,
            });
        } finally {
            setCoreLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchCoreSettings();
    }, [fetchCoreSettings]);

    const debouncedWhisperUrl = useDebounce(
        config?.ASR_BASE_URL || config?.WHISPER_BASE_URL,
        500,
    );
    const debouncedLlmBaseUrl = useDebounce(config?.LLM_BASE_URL, 500);
    const debouncedLlmProvider = useDebounce(config?.LLM_PROVIDER, 500);
    const debouncedLlmApiKey = useDebounce(config?.LLM_API_KEY, 500);
    const debouncedAsrProvider = useDebounce(config?.ASR_PROVIDER, 500);

    useEffect(() => {
        const validateUrls = async () => {
            if (
                debouncedWhisperUrl &&
                debouncedAsrProvider !== "speechmatics" &&
                debouncedAsrProvider !== "assemblyai" &&
                debouncedAsrProvider !== "local"
            ) {
                const whisperValid = await settingsApi.validateUrl(
                    "whisper",
                    debouncedWhisperUrl,
                );
                setUrlStatus((prev) => ({ ...prev, whisper: whisperValid }));
            } else {
                setUrlStatus((prev) => ({ ...prev, whisper: false }));
            }

            if (debouncedLlmBaseUrl) {
                const providerType = debouncedLlmProvider || "ollama";
                const llmValid = await settingsApi.validateUrl(
                    providerType,
                    debouncedLlmBaseUrl,
                );
                setUrlStatus((prev) => ({ ...prev, llm: llmValid }));
            } else {
                setUrlStatus((prev) => ({ ...prev, llm: false }));
            }
        };

        validateUrls();
    }, [debouncedWhisperUrl, debouncedAsrProvider, debouncedLlmBaseUrl, debouncedLlmProvider]);

    useEffect(() => {
        const refreshWhisperModels = async () => {
            if (debouncedAsrProvider === "speechmatics" || debouncedAsrProvider === "fireworks") {
                setWhisperModelsLoading(false);
                if (debouncedAsrProvider === "fireworks") {
                    setWhisperModelOptions([
                        "fireworks-asr-v2",
                        "fireworks-asr-large",
                        "whisper-v3-turbo",
                        "whisper-v3",
                    ]);
                    setWhisperModelListAvailable(true);
                } else {
                    setWhisperModelOptions([]);
                    setWhisperModelListAvailable(false);
                }
                return;
            }

            if (debouncedAsrProvider === "assemblyai") {
                setWhisperModelsLoading(false);
                setWhisperModelOptions(["universal-3-5-pro", "universal-2"]);
                setWhisperModelListAvailable(true);
                return;
            }

            if (debouncedAsrProvider === "local") {
                if (!isTauri()) {
                    setWhisperModelOptions([]);
                    setWhisperModelListAvailable(false);
                    return;
                }
                setWhisperModelsLoading(true);
                try {
                    const response = await localModelApi.fetchDownloadedWhisperModels();
                    setWhisperModelOptions(
                        (response.models || []).map((model) => model.id || model.name),
                    );
                    setWhisperModelListAvailable((response.models || []).length > 0);
                } catch (error) {
                    console.error("Error loading local ASR models:", error);
                    setWhisperModelOptions([]);
                    setWhisperModelListAvailable(false);
                } finally {
                    setWhisperModelsLoading(false);
                }
                return;
            }

            if (!debouncedWhisperUrl) {
                setWhisperModelsLoading(false);
                setWhisperModelOptions([]);
                setWhisperModelListAvailable(false);
                return;
            }

            setWhisperModelsLoading(true);
            try {
                await settingsService.fetchWhisperModels(
                    debouncedWhisperUrl,
                    setWhisperModelOptions,
                    setWhisperModelListAvailable,
                    debouncedAsrProvider,
                );
            } catch (error) {
                console.error("Error refreshing Whisper models:", error);
                setWhisperModelOptions([]);
                setWhisperModelListAvailable(false);
            } finally {
                setWhisperModelsLoading(false);
            }
        };

        refreshWhisperModels();
    }, [debouncedWhisperUrl, debouncedAsrProvider]);

    useEffect(() => {
        const refreshLlmModels = async () => {
            if ((config?.LLM_PROVIDER || "ollama") === "local") {
                return;
            }
            if (!debouncedLlmBaseUrl) {
                const provider = llmProviders.find(
                    (item) => item.id === (debouncedLlmProvider || config?.LLM_PROVIDER),
                );
                if (provider?.default_models?.length) {
                    setModelOptions(provider.default_models);
                }
                return;
            }

            setLlmModelsLoading(true);
            try {
                await settingsService.fetchLLMModels(
                    {
                        LLM_PROVIDER: debouncedLlmProvider || "ollama",
                        LLM_BASE_URL: debouncedLlmBaseUrl,
                        LLM_API_KEY: debouncedLlmApiKey,
                    },
                    setModelOptions,
                );
            } catch (error) {
                console.error("Error refreshing LLM models:", error);
                const provider = llmProviders.find(
                    (item) => item.id === (debouncedLlmProvider || config?.LLM_PROVIDER),
                );
                setModelOptions(provider?.default_models || []);
            } finally {
                setLlmModelsLoading(false);
            }
        };

        refreshLlmModels();
    }, [
        debouncedLlmBaseUrl,
        debouncedLlmProvider,
        debouncedLlmApiKey,
        config?.LLM_PROVIDER,
        llmProviders,
    ]);

    useEffect(() => {
        if (config?.LLM_PROVIDER !== "local") return;

        const fetchLocalModels = async () => {
            setLlmModelsLoading(true);
            try {
                const localModels = await localModelApi.fetchLocalModels();
                const modelNames = localModels.models.map(
                    (m) => m.name || m.filename,
                );
                setModelOptions(modelNames);
            } catch (error) {
                console.error("Error loading local models:", error);
                setModelOptions([]);
            } finally {
                setLlmModelsLoading(false);
            }
        };

        fetchLocalModels();
    }, [config?.LLM_PROVIDER]);

    const saveConfigFn = async (newConfig) => {
        if (newConfig) {
            await settingsApi.saveConfig(newConfig);
            refreshStatus();
        }
    };

    const saveNameFn = async (newName) => {
        await setClinicianName(newName);
    };

    const autosaveEnabled = !coreLoading;
    const configAutosave = useAutosave(
        config,
        saveConfigFn,
        800,
        autosaveEnabled,
    );
    const nameAutosave = useAutosave(name, saveNameFn, 800, autosaveEnabled);

    const isDirty = configAutosave.isDirty || nameAutosave.isDirty;

    useEffect(() => {
        const handler = (e) => {
            if (isDirty) {
                e.preventDefault();
                e.returnValue = "";
            }
        };
        window.addEventListener("beforeunload", handler);
        return () => window.removeEventListener("beforeunload", handler);
    }, [isDirty]);

    const handleConfigChange = (key, value) => {
        setConfig((prev) => ({
            ...prev,
            [key]: value,
        }));
    };

    useEffect(() => {
        if (!coreLoading) return;
        const t = setTimeout(() => setShowSpinner(true), 150);
        return () => clearTimeout(t);
    }, [coreLoading]);

    if (coreLoading) {
        return (
            <Center h="100dvh">
                {showSpinner && <Spinner size="xl" />}
            </Center>
        );
    }

    return (
        <Box p="5" borderRadius="sm" w="100%" maxW="1100px" mx="auto">
            <Text as="h2" mb="2">
                تنظیمات
            </Text>
            <Text color="textSecondary" mb="5">
                مدل محلی را دانلود کنید تا خودکار فعال شود، یا Groq و OpenRouter را با کلید API وصل کنید. نشانی آن‌ها از قبل آماده است.
            </Text>
            <VStack gap="5" align="stretch">
                <Box className="panels-bg" p="4" borderRadius="sm">
                    <Text as="h3" mb="3">
                        نام پزشک
                    </Text>
                    <Input
                        size="sm"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="input-style"
                        placeholder="نام خود را وارد کنید"
                    />
                </Box>

                <ModelSettingsPanel
                    isCollapsed={collapseStates.modelSettings}
                    setIsCollapsed={() =>
                        setCollapseStates((prev) => ({
                            ...prev,
                            modelSettings: !prev.modelSettings,
                        }))
                    }
                    config={config}
                    handleConfigChange={handleConfigChange}
                    modelOptions={modelOptions}
                    whisperModelOptions={whisperModelOptions}
                    whisperModelListAvailable={whisperModelListAvailable}
                    whisperModelsLoading={whisperModelsLoading}
                    llmModelsLoading={llmModelsLoading}
                    urlStatus={urlStatus}
                    llmProviders={llmProviders}
                    asrProviders={asrProviders}
                    hideExtras
                />
            </VStack>
        </Box>
    );
};

export default Settings;
