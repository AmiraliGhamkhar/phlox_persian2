import { useEffect, useState } from "react";
import { Badge } from "@chakra-ui/react";
import { Tooltip } from "@/components/ui/tooltip";
import { BsCheck2All, BsExclamationTriangle } from "react-icons/bs";
import { settingsApi } from "../../utils/api/settingsApi";

const ServiceStatus = () => {
    const [serverStatus, setServerStatus] = useState({
        whisper: false,
        llm: false,
        embedding: null,
    });

    useEffect(() => {
        const checkStatus = async () => {
            try {
                const data = await settingsApi.fetchServerStatus();
                setServerStatus(data);
            } catch (error) {
                console.error("Error checking server status:", error);
            }
        };

        checkStatus();
        const intervalId = setInterval(checkStatus, 15000);
        return () => clearInterval(intervalId);
    }, []);

    const embeddingApplicable =
        serverStatus.embedding !== null && serverStatus.embedding !== undefined;
    const allServicesUp =
        serverStatus.llm &&
        serverStatus.whisper &&
        (!embeddingApplicable || serverStatus.embedding);

    const embeddingLine = embeddingApplicable
        ? `، ${serverStatus.embedding ? "✓" : "✗"} بردارسازی`
        : "";

    return (
        <Tooltip
            content={
                allServicesUp
                    ? "همه سرویس‌ها متصل هستند"
                    : `سرویس‌ها: ${serverStatus.llm ? "✓" : "✗"} مدل زبانی، ${serverStatus.whisper ? "✓" : "✗"} تشخیص گفتار${embeddingLine}`
            }
            positioning={{ placement: "bottom" }}
        >
            <Badge
                colorPalette={allServicesUp ? "green" : "orange"}
                borderRadius="full"
                variant="subtle"
                p={1}
                aria-label={
                    allServicesUp
                        ? "همه سرویس‌ها متصل هستند"
                        : "برخی سرویس‌ها قطع هستند"
                }
            >
                {allServicesUp ? <BsCheck2All /> : <BsExclamationTriangle />}
            </Badge>
        </Tooltip>
    );
};

export default ServiceStatus;
