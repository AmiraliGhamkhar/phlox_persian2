import { Flex, Text, IconButton, HStack } from "@chakra-ui/react";
import { Tooltip } from "@/components/ui/tooltip";
import { FaEdit } from "react-icons/fa";
import { getAvatarColor, getInitials } from "../sidebar/SidebarHelpers";

const PatientInfoBar = ({ patient, onEdit }) => {
    const name = patient.name || "بیمار جدید";
    const meta = [
        patient.gender,
        patient.dob,
        patient.ur_number && `UR ${patient.ur_number}`,
    ].filter(Boolean);

    return (
        <Flex w="100%">
            <Flex
                className="panels-bg"
                borderRadius="lg"
                py={2}
                px={4}
                align="center"
                gap={3}
                w="100%"
            >
                <Flex
                    align="center"
                    justify="center"
                    boxSize="28px"
                    borderRadius="full"
                    bg={getAvatarColor(patient.name)}
                    color="#fff"
                    fontSize="xs"
                    fontWeight="700"
                    flexShrink={0}
                    css={{
                        fontFamily: '"Space Grotesk", sans-serif',
                    }}
                >
                    {(patient.name && getInitials(patient.name)) || "?"}
                </Flex>

                <HStack gap={2} minW="0">
                    <Text
                        fontWeight="700"
                        fontSize="md"
                        color={"textPrimary"}
                        lineClamp={1}
                        css={{
                            fontFamily: '"Space Grotesk", sans-serif',
                        }}
                    >
                        {name}
                    </Text>
                    <Text
                        fontSize="sm"
                        color={"textSecondary"}
                        lineClamp={1}
                        css={{
                            fontFamily: '"Vazirmatn", Tahoma, Arial, sans-serif',
                        }}
                    >
                        {meta.length
                            ? meta.join("  ·  ")
                            : "هنوز اطلاعات جمعیتی ثبت نشده است"}
                    </Text>
                </HStack>

                <Tooltip content="ویرایش جزئیات بیمار">
                    <IconButton
                        aria-label="ویرایش جزئیات بیمار"
                        size="sm"
                        variant="ghost"
                        color={"textSecondary"}
                        onClick={onEdit}
                        flexShrink={0}
                    >
                        <FaEdit />
                    </IconButton>
                </Tooltip>
            </Flex>
        </Flex>
    );
};

export default PatientInfoBar;
