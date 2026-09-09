import { useCallback, useEffect, useMemo, useState } from "react";
import { Link as RouterLink } from "react-router";
import {
    Badge,
    Box,
    Button,
    Flex,
    Heading,
    HStack,
    Input,
    SimpleGrid,
    Spinner,
    Text,
    Textarea,
    VStack,
} from "@chakra-ui/react";
import { toaster } from "@/components/ui/toaster";
import { FaCopy, FaMicrophone, FaPause, FaPlay, FaStop } from "react-icons/fa";
import MarkdownRenderer from "../components/common/MarkdownRenderer";
import { useWorkspace } from "../utils/context/workspaceContext";
import { useWorkspaceRecorder } from "../utils/hooks/useWorkspaceRecorder";
import { workspaceApi } from "../utils/api/workspaceApi";
import { useDebounce } from "../utils/hooks/useDebounce";
import { toPersianDigits } from "../i18n/fa";

const formatTimer = (seconds) => {
    const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
    const ss = String(seconds % 60).padStart(2, "0");
    return toPersianDigits(`${mm}:${ss}`);
};

const SECTION_LABELS = [
    ["chief_complaint", "شکایت اصلی"],
    ["history", "شرح‌حال"],
    ["examination", "معاینه و یافته‌ها"],
    ["assessment", "ارزیابی"],
    ["plan", "برنامه"],
];

// Persian labels for ASR flag reasons (server: server/transcription/hygiene.py).
const FLAG_LABELS = {
    low_confidence: "کم‌اعتمادی",
    suspect: "شک‌دار",
    known_hallucination_artifact: "توهم شناخته‌شده موتور صوت",
    repetition_loop: "تکرار حلقه‌ای",
    duplicated_line: "تکرار خط",
};

// Persian labels for deterministic verification findings
// (server: server/nlp_tools/verification.py).
const WARNING_KIND_LABELS = {
    number_drift: "تغییر عدد",
    unit_mismatch: "تغییر واحد",
    negation_flip: "جابه‌جایی نفی",
    ungrounded_term: "اصطلاح بدون پایه در متن",
    low_overlap_sentence: "جمله با پیوند کم به متن",
};

const WorkspacePage = () => {
    const { specialty, clinicianName, status, refreshStatus } = useWorkspace();
    const [mode, setMode] = useState("ambient");
    const [transcript, setTranscript] = useState("");
    const [report, setReport] = useState(null);
    const [fullNote, setFullNote] = useState("");
    // Deterministic faithfulness warnings for the last generated report.
    const [warnings, setWarnings] = useState([]);
    const [dictionaryHits, setDictionaryHits] = useState([]);
    const [dictQuery, setDictQuery] = useState("");
    const [dictResults, setDictResults] = useState([]);
    const [generating, setGenerating] = useState(false);
    const debouncedQuery = useDebounce(dictQuery, 300);

    const onTranscript = useCallback((text) => {
        if (!text) return;
        setTranscript(text);
    }, []);

    const recorder = useWorkspaceRecorder({ onTranscript });

    useEffect(() => {
        refreshStatus();
    }, [refreshStatus]);

    useEffect(() => {
        let cancelled = false;
        const run = async () => {
            try {
                const data = await workspaceApi.searchDictionary(debouncedQuery, 12);
                if (!cancelled) setDictResults(data?.matches || []);
            } catch {
                if (!cancelled) setDictResults([]);
            }
        };
        run();
        return () => {
            cancelled = true;
        };
    }, [debouncedQuery]);

    const specialtyLabel = useMemo(() => {
        if (!specialty) return "";
        return specialty;
    }, [specialty]);

    const handleGenerate = async () => {
        const text = transcript.trim();
        if (!text) {
            toaster.create({
                title: "متن خالی است",
                description: "ابتدا صحبت کنید یا متن پیاده‌سازی را وارد کنید.",
                type: "warning",
                duration: 4000,
            });
            return;
        }
        setGenerating(true);
        try {
            const meta = recorder.transcriptMeta || {};
            const flags = Array.isArray(meta.flags) ? meta.flags : [];
            const data = await workspaceApi.generateReport({
                transcript: text,
                specialty,
                mode,
                clinician_name: clinicianName,
                // Forward ASR hygiene metadata so the model is told which
                // spans are uncertain (W1.5) and the server can check the
                // note against the transcript (W1.1/W1.2).
                transcript_flags: flags,
                low_confidence_spans: flags
                    .map((flag) => (flag && flag.text ? String(flag.text) : ""))
                    .filter(Boolean),
            });
            setReport(data?.report || null);
            setFullNote(data?.full_note || data?.report?.full_note || "");
            setDictionaryHits(data?.dictionary || []);
            setWarnings(Array.isArray(data?.warnings) ? data.warnings : []);
        } catch (error) {
            toaster.create({
                title: "تولید گزارش ناموفق بود",
                description: error?.message || "اتصال مدل زبانی را در تنظیمات بررسی کنید.",
                type: "error",
                duration: 6000,
            });
        } finally {
            setGenerating(false);
        }
    };

    const handleCopy = async () => {
        const text = fullNote || "";
        if (!text) return;
        try {
            await navigator.clipboard.writeText(text);
            toaster.create({
                title: "کپی شد",
                description: "یادداشت کامل در کلیپ‌بورد قرار گرفت.",
                type: "success",
                duration: 2500,
            });
        } catch {
            toaster.create({
                title: "کپی ناموفق بود",
                type: "error",
                duration: 3000,
            });
        }
    };

    const asrReady = status?.asr_ready === true;
    const llmReady = status?.llm_ready === true;
    const recording = recorder.isRecording;

    return (
        <Box px={{ base: 4, md: 8 }} py={6} maxW="1400px" mx="auto">
            <VStack align="stretch" gap={5}>
                <Flex justify="space-between" align="start" wrap="wrap" gap={3}>
                    <Box>
                        <Heading as="h1" size="lg" mb={1}>
                            پیاده‌سازی و گزارش
                        </Heading>
                        <Text color="textSecondary">
                            {specialty
                                ? `تخصص فعال: ${specialtyLabel}`
                                : "ابتدا از صفحه تخصص، حوزه کاری خود را انتخاب کنید."}
                            {clinicianName ? ` — ${clinicianName}` : ""}
                        </Text>
                    </Box>
                    <HStack gap={2}>
                        <Button
                            size="sm"
                            variant={mode === "ambient" ? "solid" : "outline"}
                            colorPalette="teal"
                            onClick={() => setMode("ambient")}
                        >
                            محیطی
                        </Button>
                        <Button
                            size="sm"
                            variant={mode === "dictate" ? "solid" : "outline"}
                            colorPalette="teal"
                            onClick={() => setMode("dictate")}
                        >
                            دیکته
                        </Button>
                    </HStack>
                </Flex>

                {!specialty && (
                    <Box className="panels-bg" p={4}>
                        <Text mb={3}>برای گزارش دقیق‌تر، تخصص را انتخاب کنید.</Text>
                        <Button asChild className="nav-button" size="sm">
                            <RouterLink to="/">انتخاب تخصص</RouterLink>
                        </Button>
                    </Box>
                )}

                {(!asrReady || !llmReady) && (
                    <Box className="panels-bg" p={4}>
                        <Text mb={2}>
                            {!asrReady
                                ? "تشخیص گفتار آماده نیست. "
                                : ""}
                            {!llmReady
                                ? "مدل زبانی آماده نیست. "
                                : ""}
                            یک مدل محلی دانلود کنید یا Groq / OpenRouter را با کلید API وصل کنید.
                        </Text>
                        <Button asChild className="nav-button" size="sm">
                            <RouterLink to="/settings">رفتن به تنظیمات</RouterLink>
                        </Button>
                    </Box>
                )}

                <SimpleGrid columns={{ base: 1, lg: 2 }} gap={5}>
                    <Box className="panels-bg" p={4}>
                        <Flex justify="space-between" align="center" mb={3}>
                            <Text as="h3">متن پیاده‌سازی‌شده</Text>
                            <Text fontSize="sm" color="textSecondary">
                                {recording ? formatTimer(recorder.timer) : ""}
                            </Text>
                        </Flex>
                        {recorder.liveTranscript && recording && (
                            <Box
                                mb={3}
                                p={3}
                                borderRadius="md"
                                bg="surfaceMuted"
                                className="bidi-content"
                                dir="auto"
                            >
                                <Text fontSize="sm">{recorder.liveTranscript}</Text>
                            </Box>
                        )}
                        <Textarea
                            value={transcript}
                            onChange={(event) => setTranscript(event.target.value)}
                            minH="280px"
                            className="input-style bidi-content"
                            dir="auto"
                            placeholder="اینجا صحبت کنید یا متن را بنویسید..."
                            data-no-translate
                        />
                        <HStack mt={4} gap={2} wrap="wrap">
                            {!recording ? (
                                <Button
                                    className="green-button"
                                    onClick={recorder.startRecording}
                                    disabled={!asrReady || recorder.isTranscribing}
                                >
                                    <FaMicrophone />
                                    شروع ضبط
                                </Button>
                            ) : (
                                <>
                                    {recorder.isPaused ? (
                                        <Button className="green-button" onClick={recorder.resumeRecording}>
                                            <FaPlay />
                                            ادامه
                                        </Button>
                                    ) : (
                                        <Button className="orange-button" onClick={recorder.pauseRecording}>
                                            <FaPause />
                                            مکث
                                        </Button>
                                    )}
                                    <Button className="red-button" onClick={recorder.stopAndTranscribe}>
                                        <FaStop />
                                        توقف و پیاده‌سازی
                                    </Button>
                                </>
                            )}
                            <Button
                                className="nav-button"
                                onClick={handleGenerate}
                                loading={generating}
                                disabled={!transcript.trim() || generating}
                            >
                                تولید گزارش
                            </Button>
                            {recorder.isTranscribing && (
                                <HStack>
                                    <Spinner size="sm" />
                                    <Text fontSize="sm">در حال پیاده‌سازی...</Text>
                                </HStack>
                            )}
                        </HStack>
                        {(recorder.liveError || recorder.liveWarning) && (
                            <Text fontSize="xs" color="textSecondary" mt={2}>
                                {recorder.liveError
                                    ? `پیش‌نمایش زنده در دسترس نبود؛ پس از توقف، فایل کامل پیاده می‌شود. ${recorder.liveError}`
                                    : recorder.liveWarning}
                            </Text>
                        )}
                        {Array.isArray(recorder.transcriptMeta?.flags) &&
                            recorder.transcriptMeta.flags.length > 0 && (
                                <Box mt={3} p={3} borderRadius="md" bg="warning.50" border="1px solid" borderColor="warning.300" dir="rtl">
                                    <Text fontSize="sm" color="warning.900" fontWeight="700" mb={2}>
                                        بخش‌هایی از پیاده‌سازی نامطمئن هستند و به یادداشت ارسال‌شده علامت‌گذاری می‌شوند:
                                    </Text>
                                    <HStack gap={2} wrap="wrap">
                                        {recorder.transcriptMeta.flags.map((flag, index) => (
                                            <Badge key={`${index}-${flag.reason}`} colorPalette="orange" variant="solid">
                                                {FLAG_LABELS[flag.reason] || flag.reason}
                                                {flag.text ? `: ${flag.text}` : ""}
                                            </Badge>
                                        ))}
                                    </HStack>
                                </Box>
                            )}
                    </Box>

                    <Box className="panels-bg" p={4}>
                        <Flex justify="space-between" align="center" mb={3}>
                            <Text as="h3">گزارش بالینی</Text>
                            <Button
                                size="sm"
                                variant="ghost"
                                onClick={handleCopy}
                                disabled={!fullNote}
                            >
                                <FaCopy />
                                کپی یادداشت
                            </Button>
                        </Flex>
                        {warnings.length > 0 && (
                            <Box
                                p={3}
                                borderRadius="md"
                                bg="warning.50"
                                border="1px solid"
                                borderColor="warning.300"
                                dir="rtl"
                                data-testid="verification-warnings"
                            >
                                <Text fontSize="sm" color="warning.900" fontWeight="800" mb={2}>
                                    ⚠ نیازمند بازبینی — {warnings.length} مورد ناسازگاری با متن پیاده‌سازی یافت شد:
                                </Text>
                                <VStack align="stretch" gap={1}>
                                    {warnings.map((warning, index) => (
                                        <Text key={`${index}-${warning.kind}`} fontSize="sm" color="warning.900">
                                            • {WARNING_KIND_LABELS[warning.kind] || warning.kind}: {warning.detail}
                                        </Text>
                                    ))}
                                </VStack>
                                <Text fontSize="xs" color="warning.800" mt={2}>
                                    یادداشت ویرایش‌نشده باقی مانده است؛ بخش‌های علامت‌گذاری‌شده را پیش از ثبت در پرونده بررسی کنید.
                                </Text>
                            </Box>
                        )}
                        {generating ? (
                            <Flex py={16} justify="center">
                                <Spinner size="lg" color="teal.500" />
                            </Flex>
                        ) : fullNote ? (
                            <VStack align="stretch" gap={4}>
                                {report &&
                                    SECTION_LABELS.map(([key, label]) => {
                                        const body = report[key];
                                        if (!body) return null;
                                        return (
                                            <Box key={key}>
                                                <Text fontWeight="800" mb={1}>
                                                    {label}
                                                </Text>
                                                <Box className="markdown-content bidi-content" dir="auto">
                                                    <MarkdownRenderer>{body}</MarkdownRenderer>
                                                </Box>
                                            </Box>
                                        );
                                    })}
                                <Box>
                                    <Text fontWeight="800" mb={1}>
                                        یادداشت کامل
                                    </Text>
                                    <Box className="markdown-content bidi-content" dir="auto">
                                        <MarkdownRenderer>{fullNote}</MarkdownRenderer>
                                    </Box>
                                </Box>
                            </VStack>
                        ) : (
                            <Text color="textSecondary">
                                پس از پیاده‌سازی، دکمه «تولید گزارش» را بزنید تا یادداشت ساختاریافته ساخته شود.
                            </Text>
                        )}
                    </Box>
                </SimpleGrid>

                <Box className="panels-bg" p={4}>
                    <Text as="h3" mb={3}>
                        واژه‌نامه فارسی–انگلیسی
                    </Text>
                    <Input
                        value={dictQuery}
                        onChange={(event) => setDictQuery(event.target.value)}
                        placeholder="جست‌وجوی اصطلاح پزشکی..."
                        className="input-style"
                        mb={4}
                        data-no-translate
                    />
                    <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} gap={3}>
                        {(dictionaryHits.length && !dictQuery ? dictionaryHits : dictResults).map(
                            (item) => (
                                <Box
                                    key={`${item.fa}-${item.en}`}
                                    p={3}
                                    borderRadius="md"
                                    bg="surfaceMuted"
                                >
                                    <HStack justify="space-between" mb={1}>
                                        <Text fontWeight="700">{item.fa}</Text>
                                        {item.cat && (
                                            <Badge variant="subtle">{item.cat}</Badge>
                                        )}
                                    </HStack>
                                    <Text fontSize="sm" className="ltr-content" dir="ltr">
                                        {item.en}
                                    </Text>
                                </Box>
                            ),
                        )}
                    </SimpleGrid>
                </Box>
            </VStack>
        </Box>
    );
};

export default WorkspacePage;
