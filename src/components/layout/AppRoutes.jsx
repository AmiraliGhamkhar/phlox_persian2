import { Suspense, lazy } from "react";
import { Box, Spinner } from "@chakra-ui/react";
import { Navigate, Routes, Route } from "react-router";

const SpecialtyPage = lazy(() => import("../../pages/SpecialtyPage"));
const WorkspacePage = lazy(() => import("../../pages/WorkspacePage"));
const Settings = lazy(() => import("../../pages/Settings"));

const PageFallback = () => (
    <Box
        display="flex"
        alignItems="center"
        justifyContent="center"
        minH="60vh"
    >
        <Spinner size="lg" color="teal.500" />
    </Box>
);

const AppRoutes = () => (
    <Suspense fallback={<PageFallback />}>
        <Routes>
            <Route path="/" element={<SpecialtyPage />} />
            <Route path="/workspace" element={<WorkspacePage />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/new-note" element={<Navigate to="/" replace />} />
            <Route path="/note/:id" element={<Navigate to="/workspace" replace />} />
            <Route path="/rag" element={<Navigate to="/" replace />} />
            <Route path="/clinic-summary" element={<Navigate to="/" replace />} />
            <Route path="/outstanding-jobs" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    </Suspense>
);

export default AppRoutes;
