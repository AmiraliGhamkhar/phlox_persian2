import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";
import { workspaceApi } from "../api/workspaceApi";
import { settingsApi } from "../api/settingsApi";

const STORAGE_KEY = "phlox.specialty";

const WorkspaceContext = createContext({
    specialty: "",
    clinicianName: "",
    status: null,
    setSpecialty: async () => {},
    setClinicianName: async () => {},
    refreshStatus: async () => null,
});

const readStoredSpecialty = () => {
    try {
        return localStorage.getItem(STORAGE_KEY) || "";
    } catch {
        return "";
    }
};

export function WorkspaceProvider({ children }) {
    const [specialty, setSpecialtyState] = useState(readStoredSpecialty);
    const [clinicianName, setClinicianNameState] = useState("");
    const [status, setStatus] = useState(null);

    const persistSpecialty = (value) => {
        try {
            if (value) localStorage.setItem(STORAGE_KEY, value);
            else localStorage.removeItem(STORAGE_KEY);
        } catch {
            // ignore quota / private mode
        }
    };

    const refreshStatus = useCallback(async () => {
        try {
            const data = await workspaceApi.fetchStatus();
            setStatus(data || null);
            if (data?.specialty) {
                setSpecialtyState(data.specialty);
                persistSpecialty(data.specialty);
            }
            if (typeof data?.name === "string") {
                setClinicianNameState(data.name);
            }
            return data;
        } catch (error) {
            console.error("Workspace status failed:", error);
            return null;
        }
    }, []);

    useEffect(() => {
        refreshStatus();
    }, [refreshStatus]);

    const setSpecialty = useCallback(async (next) => {
        const value = (next || "").trim();
        setSpecialtyState(value);
        persistSpecialty(value);
        try {
            const current = await settingsApi.fetchUserSettings();
            await settingsApi.saveUserSettings({
                ...current,
                specialty: value,
            });
        } catch (error) {
            console.error("Could not save specialty:", error);
        }
        setStatus((prev) => (prev ? { ...prev, specialty: value } : prev));
    }, []);

    const setClinicianName = useCallback(async (next) => {
        const value = next || "";
        setClinicianNameState(value);
        try {
            const current = await settingsApi.fetchUserSettings();
            await settingsApi.saveUserSettings({
                ...current,
                name: value,
            });
        } catch (error) {
            console.error("Could not save clinician name:", error);
        }
        setStatus((prev) => (prev ? { ...prev, name: value } : prev));
    }, []);

    const value = useMemo(
        () => ({
            specialty,
            clinicianName,
            status,
            setSpecialty,
            setClinicianName,
            refreshStatus,
        }),
        [
            specialty,
            clinicianName,
            status,
            setSpecialty,
            setClinicianName,
            refreshStatus,
        ],
    );

    return (
        <WorkspaceContext.Provider value={value}>
            {children}
        </WorkspaceContext.Provider>
    );
}

export const useWorkspace = () => useContext(WorkspaceContext);
