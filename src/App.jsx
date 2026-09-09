import { useState, useEffect } from "react";
import { Box } from "@chakra-ui/react";

import { ApiToastProvider } from "./utils/helpers/apiToastContext";
import { AppInitContext } from "./utils/context/appInit";
import { WorkspaceProvider } from "./utils/context/workspaceContext";
import AppLayout from "./components/layout/AppLayout";
import AppRoutes from "./components/layout/AppRoutes";
import { useAppBootstrap } from "./utils/hooks/useAppBootstrap";
import { usePersianLocale } from "./i18n/fa";

function AppContent({ setIsInitializing }) {
    const bootstrap = useAppBootstrap();

    useEffect(() => {
        if (setIsInitializing) {
            setIsInitializing(bootstrap.isInitializing);
        }
    }, [bootstrap.isInitializing, setIsInitializing]);

    if (bootstrap.gate) {
        return bootstrap.gate;
    }

    if (bootstrap.isInitializing) {
        return <Box className="splash-bg" w="100vw" h="100dvh" />;
    }

    return (
        <WorkspaceProvider>
            <AppLayout>
                <AppRoutes />
            </AppLayout>
        </WorkspaceProvider>
    );
}

function App() {
    usePersianLocale();
    const [isInitializing, setIsInitializing] = useState(true);

    return (
        <AppInitContext.Provider value={{ isInitializing }}>
            <ApiToastProvider>
                <AppContent setIsInitializing={setIsInitializing} />
            </ApiToastProvider>
        </AppInitContext.Provider>
    );
}

export default App;
