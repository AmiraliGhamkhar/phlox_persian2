import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import {
    Box,
    Button,
    Heading,
    SimpleGrid,
    Spinner,
    Text,
    VStack,
} from "@chakra-ui/react";
import { workspaceApi } from "../utils/api/workspaceApi";
import { useWorkspace } from "../utils/context/workspaceContext";
import DisclaimerModal from "../components/modals/DisclaimerModal";
import { useAppInit } from "../utils/context/appInit";

const SpecialtyPage = () => {
    const navigate = useNavigate();
    const { specialty, setSpecialty } = useWorkspace();
    const { isInitializing } = useAppInit();
    const [specialties, setSpecialties] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [showDisclaimer, setShowDisclaimer] = useState(false);

    useEffect(() => {
        if (isInitializing) return;
        if (sessionStorage.getItem("disclaimerShown")) return;
        setShowDisclaimer(true);
    }, [isInitializing]);

    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            try {
                const data = await workspaceApi.fetchSpecialties();
                if (!cancelled) setSpecialties(data?.specialties || []);
            } catch (error) {
                console.error("Failed to load specialties:", error);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        load();
        return () => {
            cancelled = true;
        };
    }, []);

    const handleSelect = async (item) => {
        setSaving(true);
        try {
            await setSpecialty(item.id);
            navigate("/workspace");
        } finally {
            setSaving(false);
        }
    };

    const handleDisclaimerClose = () => {
        sessionStorage.setItem("disclaimerShown", "true");
        setShowDisclaimer(false);
    };

    return (
        <Box px={{ base: 4, md: 8 }} py={8} maxW="1100px" mx="auto">
            <DisclaimerModal isOpen={showDisclaimer} onClose={handleDisclaimerClose} />
            <VStack align="stretch" gap={6} className="anim-fade-slide-up">
                <Box>
                    <Heading as="h1" size="xl" mb={2}>
                        تخصص خود را انتخاب کنید
                    </Heading>
                    <Text color="textSecondary">
                        گزارش بالینی با همین تخصص نوشته می‌شود. بعداً از همین صفحه می‌توانید آن را عوض کنید.
                    </Text>
                </Box>
                {loading ? (
                    <Box py={16} display="flex" justifyContent="center">
                        <Spinner size="lg" color="teal.500" />
                    </Box>
                ) : (
                    <SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} gap={4} className="anim-stagger">
                        {specialties.map((item) => {
                            const selected = specialty === item.id;
                            return (
                                <Box
                                    key={item.id}
                                    as="button"
                                    textAlign="right"
                                    className="panels-bg"
                                    p={5}
                                    cursor="pointer"
                                    borderWidth="2px"
                                    borderColor={selected ? "accent" : "transparent"}
                                    _hover={{ transform: "translateY(-2px)", shadow: "md" }}
                                    transition="all 0.15s ease"
                                    disabled={saving}
                                    onClick={() => handleSelect(item)}
                                    aria-pressed={selected}
                                >
                                    <Text fontSize="lg" fontWeight="800" color="textPrimary" mb={1}>
                                        {item.fa}
                                    </Text>
                                    <Text fontSize="sm" color="textSecondary" mb={3}>
                                        {item.blurb}
                                    </Text>
                                    {selected && (
                                        <Text fontSize="xs" color="primaryButton">
                                            انتخاب فعلی
                                        </Text>
                                    )}
                                </Box>
                            );
                        })}
                    </SimpleGrid>
                )}
                {specialty && (
                    <Box>
                        <Button
                            className="green-button"
                            onClick={() => navigate("/workspace")}
                        >
                            ادامه به پیاده‌سازی
                        </Button>
                    </Box>
                )}
            </VStack>
        </Box>
    );
};

export default SpecialtyPage;
