import { useState } from "react";
import {
    Box,
    Flex,
    VStack,
    Heading,
    Text,
    Button,
    Dialog,
    Portal,
} from "@chakra-ui/react";
import { toaster } from "@/components/ui/toaster";
import { FaUserPlus, FaSearch, FaArrowLeft } from "react-icons/fa";
import { DEFAULT_TOAST_CONFIG } from "../../utils/constants";
import { CandidateRow, PathHalf } from "../patient/NewNoteStartCard";
import UrSearchField from "../patient/UrSearchField";
import DemographicsForm from "../patient/DemographicsForm";

const btnSx = {
    fontFamily: '"Space Grotesk", sans-serif',
    fontWeight: "600",
};

const NewNoteModal = ({
    isOpen,
    onClose,
    _patient,
    setPatient,
    createNewPatient,
    findPatients,
    loadSelectedPatient,
    selectedDate,
    onComplete,
}) => {

    const [view, setView] = useState("choose");
    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [isSearchLoading, setIsSearchLoading] = useState(false);
    const [confirmingId, setConfirmingId] = useState(null);
    const [draftPatient, setDraftPatient] = useState({});

    const handleFind = (e) => {
        if (e && e.preventDefault) e.preventDefault();
        const q = (query || "").trim();
        if (!q) {
            toaster.create({
                title: "شماره پرونده یا نام را وارد کنید",
                description:
                    "Type a UR number or patient name, then click search.",
                type: "warning",
                ...DEFAULT_TOAST_CONFIG,
            });
            return;
        }
        setIsSearchLoading(true);
        findPatients(q)
            .then((list) => {
                if (list && list.length > 0) {
                    setResults(list);
                    setView("results");
                } else {
                    toaster.create({
                        title: "بیماری پیدا نشد",
                        description: `بیماری با «${q}» پیدا نشد. برای ایجاد پرونده جدید، جزئیات او را وارد کنید.`,
                        type: "info",
                        ...DEFAULT_TOAST_CONFIG,
                    });
                }
            })
            .catch(() => {
                toaster.create({
                    title: "جست‌وجو ناموفق بود",
                    description: "جست‌وجوی بیماران ممکن نبود. لطفاً دوباره تلاش کنید.",
                    type: "error",
                    duration: 3000,
                });
            })
            .finally(() => setIsSearchLoading(false));
    };

    const handleConfirm = (candidate) => {
        setConfirmingId(candidate.ur_number || candidate.id);
        loadSelectedPatient(candidate, selectedDate)
            .then(() => onComplete({ cameFromSearch: true }))
            .catch(() => {
                toaster.create({
                    title: "بارگذاری بیمار ممکن نبود",
                    description: "لطفاً دوباره تلاش کنید.",
                    type: "error",
                    duration: 3000,
                });
            })
            .finally(() => setConfirmingId(null));
    };

    const handleNewPatient = () => {
        setDraftPatient({});
        setView("new-patient");
    };

    const commitNewPatient = (updated) => {
        createNewPatient()
            .then((base) => {
                setPatient({ ...base, ...updated, isNewEncounter: true });
                onComplete({ cameFromSearch: false });
            })
            .catch(() => {
                toaster.create({
                    title: "شروع بیمار جدید ممکن نبود",
                    description: "لطفاً دوباره تلاش کنید.",
                    type: "error",
                    duration: 3000,
                });
            });
    };

    const subtitle =
        view === "search"
            ? "برای یافتن بیمار موجود، شماره پرونده یا نام را وارد کنید."
            : view === "results"
              ? "برای شروع ویزیت جدید، بیمار را تأیید کنید."
              : view === "new-patient"
                ? "برای ایجاد پرونده جدید، جزئیات بیمار را وارد کنید."
                : "برای شروع ویزیت جدید، بیمار موجود را پیدا کنید یا پرونده بیمار جدیدی ایجاد کنید.";

    return (
        <Dialog.Root
            open={isOpen}
            size="lg"
            onOpenChange={(e) => {
                if (!e.open) {
                    onClose();
                }
            }}
        >
            <Portal>
                <Dialog.Backdrop />
                <Dialog.Positioner>
                    <Dialog.Content className="modal-style">
                        <Dialog.Header>
                            <Heading
                                as="h3"
                                size="xl"
                                color="textPrimary"
                                css={{
                                    fontFamily: '"Space Grotesk", sans-serif',
                                }}
                            >
                                ویزیت جدید
                            </Heading>
                        </Dialog.Header>
                        <Dialog.CloseTrigger />
                        <Dialog.Body
                            maxH="70vh"
                            overflowY="auto"
                            className="custom-scrollbar"
                        >
                            <Text
                                fontSize="sm"
                                color="textSecondary"
                                mb={4}
                                lineHeight={1.5}
                            >
                                {subtitle}
                            </Text>

                            <Box key={view}>
                                {view === "choose" ? (
                                    <Flex gap={3} mb={2}>
                                        <PathHalf
                                            icon={FaUserPlus}
                                            title="بیمار جدید"
                                            subtitle="ایجاد پرونده جدید"
                                            accent="primaryButton"
                                            tileBg="tile"
                                            onClick={handleNewPatient}
                                        />
                                        <PathHalf
                                            icon={FaSearch}
                                            title="جست‌وجو"
                                            subtitle="بیمار موجود"
                                            accent="secondaryButton"
                                            tileBg="tile"
                                            onClick={() => setView("search")}
                                        />
                                    </Flex>
                                ) : view === "search" ? (
                                    <Box>
                                        <Flex alignItems="center" asChild>
                                            <form onSubmit={handleFind}>
                                                <UrSearchField
                                                    value={query}
                                                    onChange={(e) =>
                                                        setQuery(e.target.value)
                                                    }
                                                    onSearch={handleFind}
                                                    isLoading={isSearchLoading}
                                                    autoFocus
                                                    placeholder="شماره پرونده یا نام"
                                                />
                                            </form>
                                        </Flex>
                                        <Button
                                            type="button"
                                            variant="outline"
                                            size="md"
                                            mt={3}
                                            borderRadius="2xl"
                                            className="switch-mode"
                                            css={btnSx}
                                            onClick={() => setView("choose")}
                                        >
                                            <FaArrowLeft />
                                            بازگشت
                                        </Button>
                                    </Box>
                                ) : view === "results" ? (
                                    <Box>
                                        <VStack gap={3} align="stretch">
                                            {results.map((cand) => (
                                                <CandidateRow
                                                    key={
                                                        cand.ur_number ||
                                                        cand.id
                                                    }
                                                    candidate={cand}
                                                    onConfirm={handleConfirm}
                                                    confirming={
                                                        confirmingId ===
                                                        (cand.ur_number ||
                                                            cand.id)
                                                    }
                                                    disabled={
                                                        confirmingId !== null
                                                    }
                                                />
                                            ))}
                                        </VStack>
                                        <Button
                                            type="button"
                                            variant="outline"
                                            size="md"
                                            mt={3}
                                            borderRadius="2xl"
                                            className="switch-mode"
                                            css={btnSx}
                                            onClick={() => setView("search")}
                                        >
                                            <FaArrowLeft />
                                            بازگشت
                                        </Button>
                                    </Box>
                                ) : (
                                    <DemographicsForm
                                        key={draftPatient?.id || "empty"}
                                        patient={draftPatient}
                                        setPatient={setDraftPatient}
                                        onSaved={commitNewPatient}
                                        onCancel={() => setView("choose")}
                                        cancelLabel="بازگشت"
                                        cancelIcon={<FaArrowLeft />}
                                    />
                                )}
                            </Box>
                        </Dialog.Body>
                    </Dialog.Content>
                </Dialog.Positioner>
            </Portal>
        </Dialog.Root>
    );
};

export default NewNoteModal;
