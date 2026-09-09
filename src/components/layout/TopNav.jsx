import { Box, Flex, HStack, IconButton, Image, Text } from "@chakra-ui/react";
import { NavLink } from "react-router";
import { FaMoon, FaSun } from "react-icons/fa";
import { useColorMode } from "../ui/color-mode";
import { Tooltip } from "@/components/ui/tooltip";
import ServiceStatus from "./ServiceStatus";
import { isTauri } from "../../utils/helpers/apiConfig";

const LINKS = [
    { to: "/", label: "تخصص", end: true },
    { to: "/workspace", label: "پیاده‌سازی" },
    { to: "/settings", label: "تنظیمات" },
];

const TopNav = () => {
    const { colorMode, toggleColorMode } = useColorMode();

    return (
        <Box
            as="header"
            borderBottomWidth="1px"
            borderColor="border"
            bg="secondary"
            position="sticky"
            top="0"
            zIndex="20"
            pt={isTauri() ? "18px" : "0"}
        >
            <Flex
                align="center"
                justify="space-between"
                px={{ base: 3, md: 6 }}
                py={3}
                gap={3}
                wrap="wrap"
            >
                <HStack gap={3} align="center">
                    <Image src="/logo.webp" alt="فلوکس" height="28px" />
                    <Text fontWeight="700" fontSize="lg" color="textPrimary">
                        فلوکس
                    </Text>
                    <HStack gap={1} as="nav" aria-label="صفحات اصلی">
                        {LINKS.map((link) => (
                            <NavLink
                                key={link.to}
                                to={link.to}
                                end={link.end}
                                style={{ textDecoration: "none" }}
                            >
                                {({ isActive }) => (
                                    <Box
                                        as="span"
                                        display="inline-flex"
                                        alignItems="center"
                                        px={3}
                                        py={1}
                                        borderRadius="full"
                                        fontWeight="700"
                                        fontSize="sm"
                                        bg={isActive ? "primaryButton" : "transparent"}
                                        color={isActive ? "invertedText" : "textPrimary"}
                                    >
                                        {link.label}
                                    </Box>
                                )}
                            </NavLink>
                        ))}
                    </HStack>
                </HStack>
                <HStack gap={3}>
                    <Tooltip
                        content={
                            colorMode === "light"
                                ? "تغییر به حالت تاریک"
                                : "تغییر به حالت روشن"
                        }
                    >
                        <IconButton
                            aria-label="تغییر حالت رنگ"
                            variant="ghost"
                            size="sm"
                            onClick={toggleColorMode}
                        >
                            {colorMode === "light" ? <FaMoon /> : <FaSun />}
                        </IconButton>
                    </Tooltip>
                    <ServiceStatus />
                </HStack>
            </Flex>
        </Box>
    );
};

export default TopNav;
