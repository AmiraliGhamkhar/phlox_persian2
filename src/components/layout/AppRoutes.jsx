import { Suspense, lazy } from "react";
import { Box, Spinner } from "@chakra-ui/react";
import { Routes, Route } from "react-router";

const LandingPage = lazy(() => import("../../pages/LandingPage"));
const PatientDetails = lazy(() => import("../../pages/PatientDetails"));
const Settings = lazy(() => import("../../pages/Settings"));
const Rag = lazy(() => import("../../pages/Rag"));
const ClinicSummary = lazy(() => import("../../pages/ClinicSummary"));
const OutstandingJobs = lazy(() => import("../../pages/OutstandingJobs"));

const PageFallback = () => (
    <Box
        display="flex"
        alignItems="center"
        justifyContent="center"
        minH="100vh"
    >
        <Spinner size="lg" color="teal.500" />
    </Box>
);

const AppRoutes = ({
    patient,
    setPatient,
    selectedDate,
    refreshSidebar,
    setIsModified,
    onResetLetter,
    onOpenNewNoteModal,
    newNoteKey,
    handleSelectPatient,
}) => (
    <Suspense fallback={<PageFallback />}>
        <Routes>
            <Route
                path="/new-note"
                element={
                    <PatientDetails
                        key={`new-note-${newNoteKey}`}
                        patient={patient}
                        setPatient={setPatient}
                        selectedDate={selectedDate}
                        refreshSidebar={refreshSidebar}
                        setIsModified={setIsModified}
                        onResetLetter={onResetLetter}
                        onOpenNewNoteModal={onOpenNewNoteModal}
                    />
                }
            />
            <Route
                path="/note/:id"
                element={
                    <PatientDetails
                        patient={patient}
                        setPatient={setPatient}
                        selectedDate={selectedDate}
                        refreshSidebar={refreshSidebar}
                        setIsModified={setIsModified}
                        onOpenNewNoteModal={onOpenNewNoteModal}
                    />
                }
            />
            <Route path="/" element={<LandingPage />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/rag" element={<Rag />} />
            <Route
                path="/clinic-summary"
                element={
                    <ClinicSummary
                        selectedDate={selectedDate}
                        handleSelectPatient={handleSelectPatient}
                        refreshSidebar={refreshSidebar}
                    />
                }
            />
            <Route
                path="/outstanding-jobs"
                element={
                    <OutstandingJobs
                        handleSelectPatient={(patient) =>
                            handleSelectPatient(patient, true)
                        }
                        refreshSidebar={refreshSidebar}
                    />
                }
            />
        </Routes>
    </Suspense>
);

export default AppRoutes;
