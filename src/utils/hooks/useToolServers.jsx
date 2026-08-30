import { useState, useCallback, useMemo } from "react";
import useSWR from "swr";
import { toolsApi } from "../api/toolsApi";
import { settingsApi } from "../api/settingsApi";
import { toastApiError, toastApiSuccess } from "../helpers/errorHandlers";
import { KEYS } from "../cache/keys";

const DEFAULT_DISABLED_TOOLS = ["pubmed_search", "wiki_search"];

export const useToolServers = () => {
    const [isLoading, setIsLoading] = useState(false);
    const [testingServerId, setTestingServerId] = useState(null);

    const {
        data: toolServers = [],
        mutate: mutateServers,
    } = useSWR(KEYS.TOOL_SERVERS, async () => {
        const data = await toolsApi.fetchToolServers();
        return data.servers || [];
    });

    const {
        data: userSettings = {},
        mutate: mutateUserSettings,
    } = useSWR(KEYS.USER_SETTINGS, () => settingsApi.fetchUserSettings());

    const {
        data: cachedMcpTools = [],
        mutate: mutateCachedTools,
    } = useSWR(KEYS.MCP_CACHED_TOOLS, async () => {
        const data = await toolsApi.fetchCachedTools();
        return data?.tools || [];
    });

    const disabledTools = useMemo(
        () => userSettings.disabled_tools || DEFAULT_DISABLED_TOOLS,
        [userSettings],
    );

    const refreshServers = useCallback(async () => {
        await mutateServers();
    }, [mutateServers]);

    const addServer = useCallback(
        async (serverData) => {
            setIsLoading(true);
            try {
                await toolsApi.addToolServer(serverData);
                await toolsApi.refreshTools();
                toastApiSuccess("Tool server added successfully");
                await Promise.all([mutateServers(), mutateCachedTools()]);
                return true;
            } catch (error) {
                console.error("Error adding tool server:", error);
                toastApiError("Failed to add tool server");
                return false;
            } finally {
                setIsLoading(false);
            }
        },
        [mutateServers, mutateCachedTools],
    );

    const deleteServer = useCallback(
        async (serverId) => {
            setIsLoading(true);
            try {
                await toolsApi.deleteToolServer(serverId);
                await toolsApi.refreshTools();
                toastApiSuccess("Tool server deleted");
                await Promise.all([mutateServers(), mutateCachedTools()]);
                return true;
            } catch (error) {
                console.error("Error deleting tool server:", error);
                toastApiError("Failed to delete tool server");
                return false;
            } finally {
                setIsLoading(false);
            }
        },
        [mutateServers, mutateCachedTools],
    );

    const toggleServer = useCallback(
        async (serverId, enabled) => {
            setIsLoading(true);
            try {
                await toolsApi.toggleToolServer(serverId, enabled);
                await toolsApi.refreshTools();
                toastApiSuccess(`Tool server ${enabled ? "enabled" : "disabled"}`);
                await Promise.all([mutateServers(), mutateCachedTools()]);
                return true;
            } catch (error) {
                console.error("Error toggling tool server:", error);
                toastApiError("Failed to toggle tool server");
                return false;
            } finally {
                setIsLoading(false);
            }
        },
        [mutateServers, mutateCachedTools],
    );

    const toggleSensitiveData = useCallback(
        async (serverId, allowSensitive) => {
            setIsLoading(true);
            try {
                await toolsApi.updateToolServer(serverId, {
                    allow_sensitive_data: allowSensitive,
                });
                await toolsApi.refreshTools();
                toastApiSuccess(
                    `Sensitive data ${allowSensitive ? "allowed" : "sanitized"}`,
                );
                await Promise.all([mutateServers(), mutateCachedTools()]);
                return true;
            } catch (error) {
                console.error("Error toggling sensitive data:", error);
                toastApiError("Failed to update sensitive data setting");
                return false;
            } finally {
                setIsLoading(false);
            }
        },
        [mutateServers, mutateCachedTools],
    );

    const testServer = useCallback(async (serverId) => {
        setTestingServerId(serverId);
        try {
            const result = await toolsApi.testToolServer(serverId);
            if (result.success) {
                const toolCount = result.tools?.length || 0;
                const serverName = result.server_info?.name || "";
                const serverVersion = result.server_info?.version || "";
                const description = serverName
                    ? `${serverName}${serverVersion ? ` v${serverVersion}` : ""} - ${toolCount} tools`
                    : `Found ${toolCount} tools`;
                toastApiSuccess(description, "Connection Successful");
                await toolsApi.refreshTools();
                await Promise.all([mutateServers(), mutateCachedTools()]);
                return true;
            }
            toastApiError(
                result.message || "Failed to connect to server",
                "Connection Failed",
            );
            return false;
        } catch (error) {
            console.error("Error testing tool server:", error);
            toastApiError("Failed to test tool server");
            return false;
        } finally {
            setTestingServerId(null);
        }
    }, [mutateServers, mutateCachedTools]);

    const toggleBuiltInTool = useCallback(
        async (toolName, enabled) => {
            const newDisabledTools = enabled
                ? disabledTools.filter((t) => t !== toolName)
                : [...disabledTools, toolName];

            try {
                await settingsApi.saveUserSettings({
                    ...userSettings,
                    disabled_tools: newDisabledTools,
                });
                // Optimistic local update; full revalidate via mutate
                mutateUserSettings(
                    (prev) => ({ ...prev, disabled_tools: newDisabledTools }),
                    { revalidate: false },
                );
                toastApiSuccess(`${toolName} ${enabled ? "enabled" : "disabled"}`);
                return true;
            } catch (error) {
                console.error("Error saving tool settings:", error);
                toastApiError("Failed to save tool settings");
                return false;
            }
        },
        [disabledTools, userSettings, mutateUserSettings],
    );

    const isToolEnabled = useCallback(
        (toolName) => !disabledTools.includes(toolName),
        [disabledTools],
    );

    const toggleMcpTool = useCallback(
        async (serverId, toolName, enabled) => {
            try {
                await toolsApi.toggleMcpTool(serverId, toolName, enabled);
                await mutateServers();
                toastApiSuccess(
                    `${toolName} ${enabled ? "enabled" : "disabled"}`,
                );
                return true;
            } catch (error) {
                console.error("Error toggling MCP tool:", error);
                toastApiError("Failed to update MCP tool");
                return false;
            }
        },
        [mutateServers],
    );

    return {
        toolServers,
        cachedMcpTools,
        isLoading,
        testingServerId,
        userSettings,
        disabledTools,
        addServer,
        deleteServer,
        toggleServer,
        toggleSensitiveData,
        testServer,
        toggleBuiltInTool,
        toggleMcpTool,
        isToolEnabled,
        refreshServers,
    };
};
