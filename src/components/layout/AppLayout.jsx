import { Box, Flex } from "@chakra-ui/react";
import TopNav from "./TopNav";
import { isTauri } from "../../utils/helpers/apiConfig";

const AppLayout = ({ children }) => {
    return (
        <Flex direction="column" minH="100dvh" position="relative" bg={isTauri() ? "base" : "transparent"}>
            {isTauri() && (
                <Box
                    data-tauri-drag-region
                    height="25px"
                    position="fixed"
                    top="0"
                    left="0"
                    right="0"
                    zIndex="1000"
                />
            )}
            <TopNav />
            <Box
                flex="1"
                className="main-bg"
                overflowY="auto"
                position="relative"
            >
                {children}
            </Box>
        </Flex>
    );
};

export default AppLayout;
