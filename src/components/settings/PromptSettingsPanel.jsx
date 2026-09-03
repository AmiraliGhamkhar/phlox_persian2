// Component for managing and editing prompts for LLMs.
import { useState } from "react";
import { Box, Flex, IconButton, Text, Collapsible, Textarea, Button, Tabs, NumberInput, HStack, VStack, Alert } from "@chakra-ui/react";
import { Tooltip } from '@/components/ui/tooltip';
import { ChevronRightIcon, ChevronDownIcon } from "../common/icons";
import {
  FaPencilAlt,
  FaFileAlt,
  FaComments,
  FaEnvelope,
  FaCog,
} from "react-icons/fa";
import { FiRefreshCw } from "react-icons/fi";

const ResetToDefaultButton = ({
  onClick,
  children = "بازنشانی به پیش‌فرض",
  ...props
}) => (
  <Button
    size="sm"
    h="30px"
    minH="30px"
    className="red-button"
    onClick={onClick}
    {...props}><FiRefreshCw />{children}</Button>
);

const PromptSettingsPanel = ({
  isCollapsed,
  setIsCollapsed,
  prompts,
  handlePromptChange,
  handlePromptReset,
  options,
  handleOptionChange,
  handleOptionsReset,
  _config,
}) => {
  const [tabIndex, setTabIndex] = useState("0");

  return (
    <Box className="panels-bg" p="4" borderRadius="sm">
      <Flex align="center" justify="space-between">
        <Flex align="center">
          <IconButton
            onClick={() => setIsCollapsed(!isCollapsed)}
            aria-label="باز و بسته کردن بخش"
            variant="outline"
            size="sm"
            mr="2"
            className="collapse-toggle">{isCollapsed ? <ChevronRightIcon /> : <ChevronDownIcon />}</IconButton>
          <FaPencilAlt size="1.2em" style={{ marginRight: "5px" }} />
          <Text as="h3">تنظیمات دستورها</Text>
        </Flex>
      </Flex>
      <Collapsible.Root open={!isCollapsed}>
        <Collapsible.Content>
          <Alert.Root status="warning" mt={4} borderRadius="sm">
            <Alert.Indicator color="secondaryButton" />
            <Alert.Description fontSize="sm">
              این دستورها پیش‌فرض‌های با دقت تنظیم‌شده هستند. توصیه می‌کنیم
              مگر برای دلیل مشخص آن‌ها را تغییر ندهید.
            </Alert.Description>
          </Alert.Root>
          <Tabs.Root
            variant='enclosed'
            mt={4}
            value={tabIndex}
            onValueChange={({ value }) => setTabIndex(value)}
          >
            <Tabs.List>
              <Tooltip content="دستور سیستم برای بهبود خروجی‌های تولیدشده">
                <Tabs.Trigger className="tab-style" value="0">
                  <HStack>
                    <FaPencilAlt />
                    <Text>بهبود متن</Text>
                  </HStack>
                </Tabs.Trigger>
              </Tooltip>
              <Tooltip content="دستور سیستم برای تولید خلاصه‌ها">
                <Tabs.Trigger className="tab-style" value="1">
                  <HStack>
                    <FaFileAlt />
                    <Text>خلاصه</Text>
                  </HStack>
                </Tabs.Trigger>
              </Tooltip>
              <Tooltip content="دستور سیستم برای گفت‌وگو">
                <Tabs.Trigger className="tab-style" value="2">
                  <HStack>
                    <FaComments />
                    <Text>گفت‌وگو</Text>
                  </HStack>
                </Tabs.Trigger>
              </Tooltip>
              <Tooltip content="دستور سیستم برای تولید نامه‌ها">
                <Tabs.Trigger className="tab-style" value="3">
                  <HStack>
                    <FaEnvelope />
                    <Text>نامه</Text>
                  </HStack>
                </Tabs.Trigger>
              </Tooltip>
              <Tooltip content="تنظیمات فنی پیکربندی مدل">
                <Tabs.Trigger className="tab-style" value="4">
                  <HStack>
                    <FaCog />
                    <Text>پیشرفته</Text>
                  </HStack>
                </Tabs.Trigger>
              </Tooltip>
            </Tabs.List>
            
              <Tabs.Content value="0" className="floating-main">
                <VStack gap={4} align="stretch">
                  <Flex justify="space-between" align="center">
                    <Box>
                      <Text fontSize="md" fontWeight="bold">
                        دستور بهبود متن
                      </Text>
                      <Text fontSize="sm" color="overlay0">
                        دستور سیستم برای بهبود خروجی‌های تولیدشده
                      </Text>
                    </Box>
                    <ResetToDefaultButton
                      onClick={() =>
                        handlePromptReset && handlePromptReset("refinement")
                      }
                    />
                  </Flex>
                  <Textarea
                    value={prompts?.refinement?.system || ""}
                    onChange={(e) =>
                      handlePromptChange("refinement", "system", e.target.value)
                    }
                    rows={10}
                    className="textarea-style"
                  />
                </VStack>
              </Tabs.Content>

              <Tabs.Content value="1" className="floating-main">
                <VStack gap={4} align="stretch">
                  <Flex justify="space-between" align="center">
                    <Box>
                      <Text fontSize="md" fontWeight="bold">
                        دستور خلاصه
                      </Text>
                      <Text fontSize="sm" color="overlay0">
                        دستور سیستم برای تولید خلاصه‌ها
                      </Text>
                    </Box>
                    <ResetToDefaultButton
                      onClick={() =>
                        handlePromptReset && handlePromptReset("summary")
                      }
                    />
                  </Flex>
                  <Textarea
                    value={prompts?.summary?.system || ""}
                    onChange={(e) =>
                      handlePromptChange("summary", "system", e.target.value)
                    }
                    rows={10}
                    className="textarea-style"
                  />
                </VStack>
              </Tabs.Content>

              <Tabs.Content value="2" className="floating-main">
                <VStack gap={4} align="stretch">
                  <Flex justify="space-between" align="center">
                    <Box>
                      <Text fontSize="md" fontWeight="bold">
                        دستور گفت‌وگو
                      </Text>
                      <Text fontSize="sm" color="overlay0">
                        دستور سیستم برای گفت‌وگو
                      </Text>
                    </Box>
                    <ResetToDefaultButton
                      onClick={() =>
                        handlePromptReset && handlePromptReset("chat")
                      }
                    />
                  </Flex>
                  <Textarea
                    value={prompts?.chat?.system || ""}
                    onChange={(e) =>
                      handlePromptChange("chat", "system", e.target.value)
                    }
                    rows={10}
                    className="textarea-style"
                  />
                </VStack>
              </Tabs.Content>

              <Tabs.Content value="3" className="floating-main">
                <VStack gap={4} align="stretch">
                  <Flex justify="space-between" align="center">
                    <Box>
                      <Text fontSize="md" fontWeight="bold">
                        دستور نامه
                      </Text>
                      <Text fontSize="sm" color="overlay0">
                        دستور سیستم برای تولید نامه‌ها
                      </Text>
                    </Box>
                    <ResetToDefaultButton
                      onClick={() =>
                        handlePromptReset && handlePromptReset("letter")
                      }
                    />
                  </Flex>
                  <Textarea
                    value={prompts?.letter?.system || ""}
                    onChange={(e) =>
                      handlePromptChange("letter", "system", e.target.value)
                    }
                    rows={10}
                    className="textarea-style"
                  />
                </VStack>
              </Tabs.Content>

              <Tabs.Content value="4" className="floating-main">
                <VStack gap={6} align="stretch">
                  <Flex justify="space-between" align="center">
                    <Text fontSize="md" fontWeight="bold">
                      پیکربندی مدل
                    </Text>
                    <ResetToDefaultButton
                      onClick={() =>
                        handleOptionsReset && handleOptionsReset()
                      }
                    />
                  </Flex>

                  <Box>
                    <Text fontSize="sm" fontWeight="bold" mb={2}>
                      مدل اصلی
                    </Text>
                    <Text fontSize="xs" color="overlay0" mb={2}>
                      اندازه پنجرهٔ بافت (Context Window) مدل اصلی
                    </Text>
                    <HStack>
                      <Text fontSize="sm">num_ctx</Text>
                      <NumberInput.Root
                        size="sm"
                        value={String(options?.general?.num_ctx)}
                        onValueChange={(newValue) =>
                          handleOptionChange("general", "num_ctx", newValue)
                        }
                      >
                        <NumberInput.Input className="input-style" width="100px" />
                      </NumberInput.Root>
                    </HStack>
                  </Box>

                  <Box>
                    <Text fontSize="sm" fontWeight="bold" mb={2}>
                      مدل ثانویه
                    </Text>
                    <Text fontSize="xs" color="overlay0" mb={2}>
                      اندازه پنجرهٔ بافت (Context Window) مدل ثانویه
                    </Text>
                    <HStack>
                      <Text fontSize="sm">num_ctx</Text>
                      <NumberInput.Root
                        size="sm"
                        value={String(options?.secondary?.num_ctx)}
                        onValueChange={(newValue) =>
                          handleOptionChange("secondary", "num_ctx", newValue)
                        }
                      >
                        <NumberInput.Input className="input-style" width="100px" />
                      </NumberInput.Root>
                    </HStack>
                  </Box>

                  <Box>
                    <Text fontSize="sm" fontWeight="bold" mb={2}>
                      تولید نامه
                    </Text>
                    <Text fontSize="xs" color="overlay0" mb={2}>
                      دمای مدل تولید نامه
                    </Text>
                    <HStack>
                      <Text fontSize="sm">temperature</Text>
                      <NumberInput.Root
                        size="sm"
                        value={String(options?.letter?.temperature)}
                        onValueChange={(newValue) =>
                          handleOptionChange("letter", "temperature", newValue)
                        }
                      >
                        <NumberInput.Input className="input-style" width="100px" />
                      </NumberInput.Root>
                    </HStack>
                  </Box>
                </VStack>
              </Tabs.Content>
            
          </Tabs.Root>
        </Collapsible.Content>
      </Collapsible.Root>
    </Box>
  );
};

export default PromptSettingsPanel;
