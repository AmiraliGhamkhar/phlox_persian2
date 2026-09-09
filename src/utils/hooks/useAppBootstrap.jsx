import { useState, useEffect, useCallback } from "react";
import { Box } from "@chakra-ui/react";
import { toaster } from "@/components/ui/toaster";
import { invoke } from "@tauri-apps/api/core";
import EncryptionSetup from "../../components/setup/EncryptionSetup";
import EncryptionUnlock from "../../components/setup/EncryptionUnlock";
import ServerStartupLoader from "../../components/setup/ServerStartupLoader";
import { settingsApi } from "../api/settingsApi";
import { isTauri } from "../../utils/helpers/apiConfig";
import { setEmbeddingReady } from "../../utils/helpers/featureFlags";
import { encryptionApi } from "../../utils/api/encryptionApi";
import { localModelApi } from "../../utils/api/localModelApi";

export const useAppBootstrap = () => {
    const [showSplashScreen, setShowSplashScreen] = useState(undefined);
    const [, setIsLoadingSplashCheck] = useState(!isTauri());
    const [, setEncryptionStatus] = useState(null);
    const [showEncryptionSetup, setShowEncryptionSetup] = useState(false);
    const [showEncryptionUnlock, setShowEncryptionUnlock] = useState(false);
    const [, setIsLoadingEncryptionCheck] = useState(!isTauri());
    const [isCheckingEncryptionStatus, setIsCheckingEncryptionStatus] =
        useState(isTauri());
    const [showServerStartupLoader, setShowServerStartupLoader] =
        useState(false);
    const [isInGracePeriod, setIsInGracePeriod] = useState(isTauri());

    // App initialization state - true when server is not ready yet.
    const isInitializing =
        showEncryptionSetup ||
        showEncryptionUnlock ||
        showServerStartupLoader ||
        isInGracePeriod;

    const checkSplashStatus = useCallback(async () => {
        // The simplified three-page product skips first-run splash/chat setup.
        setShowSplashScreen(false);
        setIsLoadingSplashCheck(false);
        try {
            const userData = await settingsApi.fetchUserSettings();
            if (userData && userData.has_completed_splash_screen === false) {
                await settingsApi.markSplashCompleted();
            }
        } catch (error) {
            console.warn("Could not mark splash complete:", error);
        }
    }, []);

    // Only check splash status on mount if NOT in Tauri
    // In Tauri, we wait until after encryption unlock is complete
    useEffect(() => {
        if (!isTauri()) {
            checkSplashStatus();
        }
    }, [checkSplashStatus]);

    useEffect(() => {
        if (!isTauri()) {
            return;
        }

        const checkEncryptionStatus = async () => {
            try {
                const status = await encryptionApi.getStatus();
                setEncryptionStatus(status);

                if (!status.has_setup && !status.has_database) {
                    setShowEncryptionSetup(true);
                } else if (status.has_setup && !status.has_keychain) {
                    try {
                        await invoke("start_server_command");
                        console.log(
                            "Server started in warm mode, waiting for passphrase",
                        );
                    } catch (e) {
                        console.warn("Failed to warm start server:", e);
                    }
                    setShowEncryptionUnlock(true);
                } else {
                    checkSplashStatus();
                    setIsInGracePeriod(false);
                }
            } catch (error) {
                console.error("Error checking encryption status:", error);
            } finally {
                setIsLoadingEncryptionCheck(false);
                setIsCheckingEncryptionStatus(false);
            }
        };

        checkEncryptionStatus();
    }, []);

    const handleEncryptionSetupComplete = () => {
        setShowEncryptionSetup(false);
        setShowServerStartupLoader(true);
    };

    const handleEncryptionUnlockComplete = () => {
        setShowEncryptionUnlock(false);
        setShowServerStartupLoader(true);
    };

    const handleServerReady = () => {
        setShowServerStartupLoader(false);
        checkSplashStatus();

        // Sync embedding model status for RAG feature flag (Tauri only)
        if (isTauri()) {
            localModelApi.fetchEmbeddingStatus()
                .then((res) => {
                    const has = !!res?.downloaded;
                    setEmbeddingReady(has);
                })
                .catch(() => {});
        }

        setTimeout(() => {
            setIsInGracePeriod(false);
        }, 2000); // 2 second grace period
    };

    const handleServerError = (error) => {
        console.error("Server startup error:", error);
        setShowServerStartupLoader(false);
        // Show error toast
        toaster.create({
            title: "Server Error",
            description: error.message || "Failed to start the server",
            type: "error",
            duration: 5000,
        });
        // Go back to unlock screen
        setShowEncryptionUnlock(true);
    };

    let gate = null;
    if (isCheckingEncryptionStatus) {
        gate = <Box className="splash-bg" w="100vw" h="100dvh" />;
    } else if (showEncryptionSetup) {
        gate = <EncryptionSetup onComplete={handleEncryptionSetupComplete} />;
    } else if (showEncryptionUnlock) {
        gate = <EncryptionUnlock onComplete={handleEncryptionUnlockComplete} />;
    } else if (showServerStartupLoader) {
        gate = (
            <ServerStartupLoader
                onReady={handleServerReady}
                onError={handleServerError}
            />
        );
    } else if (showSplashScreen) {
        gate = null;
    }

    return { isInitializing, gate };
};
