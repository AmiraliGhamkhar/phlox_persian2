// Component for configuring user-specific settings.
import { Box, Flex, HStack, IconButton, Text, Collapsible, Input, NativeSelect, Switch, Tabs, VStack, Field } from "@chakra-ui/react";
import { ChevronRightIcon, ChevronDownIcon } from "../common/icons";
import { FaUser, FaCog, FaFileAlt, FaEnvelopeOpenText, FaComments } from "react-icons/fa";
import TemplateSettingsPanel from "./TemplateSettingsPanel";
import LetterTemplatesPanel from "./LetterTemplatesPanel";
import ChatSettingsPanel from "./ChatSettingsPanel";
import { isChatEnabled } from "../../utils/helpers/featureFlags";

const ADVANCED_OPTIONS_SCHEMA = [
  {
    key: "store_original_pdfs",
    label: "ذخیره PDFهای اصلی",
    description:
      "پس از بارگذاری، فایل‌های اصلی PDF را در پایگاه داده نگه می‌دارد و فضای بیشتری مصرف می‌کند.",
    type: "boolean",
    defaultValue: false,
  },
  {
    key: "require_scribe_consent",
    label: "نیاز به رضایت بیمار برای ثبت محیطی",
    description:
      "پیش از ضبط محیطی از هر بیمار رضایت می‌گیرد. دیکته تحت تأثیر نیست و رضایت برای هر بیمار ذخیره می‌شود.",
    type: "boolean",
    defaultValue: false,
  },
];

const UserSettingsPanel = ({
  isCollapsed,
  setIsCollapsed,
  userSettings,
  setUserSettings,
  specialties,
  templates,
  letterTemplates,
  setTemplates,
}) => {
  const handleDefaultTemplateChange = (templateKey) => {
    setUserSettings((prev) => ({
      ...prev,
      default_template: templateKey,
    }));
  };
  const handleDefaultLetterTemplateChange = (templateId) => {
    setUserSettings((prev) => ({
      ...prev,
      default_letter_template_id: templateId,
    }));
  };
  const handleAdvancedOptionChange = (key, value) => {
    setUserSettings((prev) => ({
      ...prev,
      advanced_options: {
        ...(prev.advanced_options || {}),
        [key]: value,
      },
    }));
  };
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
          <FaUser size="1.2em" style={{ marginRight: "5px" }} />
          <Text as="h3">تنظیمات کاربر</Text>
        </Flex>
      </Flex>
      <Collapsible.Root open={!isCollapsed}>
        <Collapsible.Content>
          <Tabs.Root variant='enclosed' mt={4} defaultValue="0">
            <Tabs.List>
              <Tabs.Trigger className="tab-style" value="0" data-testid="user-tab-general">
                <HStack>
                  <FaUser />
                  <Text>عمومی</Text>
                </HStack>
              </Tabs.Trigger>
              <Tabs.Trigger className="tab-style" value="2" data-testid="user-tab-note-templates">
                <HStack>
                  <FaFileAlt />
                  <Text>قالب‌های یادداشت</Text>
                </HStack>
              </Tabs.Trigger>
              <Tabs.Trigger className="tab-style" value="3" data-testid="user-tab-letter-templates">
                <HStack>
                  <FaEnvelopeOpenText />
                  <Text>قالب‌های نامه</Text>
                </HStack>
              </Tabs.Trigger>
              {isChatEnabled() && (
                <Tabs.Trigger className="tab-style" value="4" data-testid="user-tab-quick-chat">
                  <HStack>
                    <FaComments />
                    <Text>گفت‌وگوی سریع</Text>
                  </HStack>
                </Tabs.Trigger>
              )}
              <Tabs.Trigger className="tab-style" value="1" data-testid="user-tab-advanced">
                <HStack>
                  <FaCog />
                  <Text>پیشرفته</Text>
                </HStack>
              </Tabs.Trigger>
            </Tabs.List>
            
              <Tabs.Content value="0" className="floating-main">
                <VStack gap={4} align="stretch">
                  <Box>
                    <Text fontSize="sm" mb="1">
                      Name
                    </Text>
                    <Input
                      size="sm"
                      value={userSettings.name || ""}
                      onChange={(e) =>
                        setUserSettings((prev) => ({
                          ...prev,
                          name: e.target.value,
                        }))
                      }
                      className="input-style"
                      placeholder="نام خود را وارد کنید"
                      data-testid="user-name-input"
                    />
                  </Box>
                  <Box>
                    <Text fontSize="sm" mb="1">
                      Specialty
                    </Text>
                    <NativeSelect.Root>
                      <NativeSelect.Field
                        size="sm"
                        value={userSettings.specialty || ""}
                        onChange={(e) =>
                          setUserSettings((prev) => ({
                            ...prev,
                            specialty: e.target.value,
                          }))
                        }
                        className="input-style"
                        placeholder="تخصص خود را انتخاب کنید"
                        data-testid="user-specialty-select">
                        {specialties.map((specialty) => (
                          <option key={specialty} value={specialty}>
                            {specialty}
                          </option>
                        ))}
                      </NativeSelect.Field>
                      <NativeSelect.Indicator />
                    </NativeSelect.Root>
                  </Box>
                  <Field.Root>
                    <Field.Label fontSize="sm" fontWeight={"bold"}>
                      Default Template
                    </Field.Label>
                    <NativeSelect.Root>
                      <NativeSelect.Field
                        size="sm"
                        value={userSettings.default_template || ""}
                        onChange={(e) => handleDefaultTemplateChange(e.target.value)}
                        className="input-style"
                        placeholder="قالب پیش‌فرض را انتخاب کنید"
                        data-testid="user-default-template-select">
                        {/* Change this part to map over templates array correctly */}
                        {templates.map((template) => (
                          <option
                            key={template.template_key}
                            value={template.template_key}
                          >
                            {template.template_name}
                          </option>
                        ))}
                      </NativeSelect.Field>
                      <NativeSelect.Indicator />
                    </NativeSelect.Root>
                  </Field.Root>
                  <Field.Root>
                    <Field.Label fontSize="sm" fontWeight={"bold"}>
                      قالب پیش‌فرض نامه
                    </Field.Label>
                    <NativeSelect.Root>
                      <NativeSelect.Field
                        size="sm"
                        value={userSettings.default_letter_template_id || ""}
                        onChange={(e) =>
                          handleDefaultLetterTemplateChange(e.target.value)
                        }
                        className="input-style"
                        placeholder="قالب پیش‌فرض نامه را انتخاب کنید"
                        data-testid="user-default-letter-template-select">
                        {letterTemplates.map((template) => (
                          <option key={template.id} value={template.id}>
                            {template.name}
                          </option>
                        ))}
                      </NativeSelect.Field>
                      <NativeSelect.Indicator />
                    </NativeSelect.Root>
                  </Field.Root>
                </VStack>
              </Tabs.Content>
              <Tabs.Content value="1" className="floating-main">
                <Text fontSize="sm" mb={4} className="pill-box-icons">
                  این گزینه‌ها برای کاربران پیشرفته هستند و تغییرشان ممکن است
                  بر فضای ذخیره‌سازی یا عملکرد اثر بگذارد.
                </Text>
                <VStack gap={3} align="stretch">
                  {ADVANCED_OPTIONS_SCHEMA.map((option) => (
                    <Flex key={option.key} justify="space-between" align="center">
                      <Box>
                        <Text fontSize="sm" fontWeight="medium">
                          {option.label}
                        </Text>
                        <Text fontSize="xs" className="pill-box-icons">
                          {option.description}
                        </Text>
                      </Box>
                      <Switch.Root
                        size="sm"
                        data-testid={`user-advanced-option-${option.key}`}
                        checked={
                          userSettings.advanced_options?.[option.key] ??
                          option.defaultValue
                        }
                        onCheckedChange={({ checked }) =>
                          handleAdvancedOptionChange(option.key, checked)
                        }
                      >
                        <Switch.HiddenInput />
                        <Switch.Control>
                          <Switch.Thumb />
                        </Switch.Control>
                      </Switch.Root>
                    </Flex>
                  ))}
                </VStack>
              </Tabs.Content>
            
              <Tabs.Content value="2" className="floating-main">
                <TemplateSettingsPanel
                  templates={templates}
                  setTemplates={setTemplates}
                />
              </Tabs.Content>
              <Tabs.Content value="3" className="floating-main">
                <LetterTemplatesPanel />
              </Tabs.Content>
              {isChatEnabled() && (
                <Tabs.Content value="4" className="floating-main">
                  <ChatSettingsPanel
                    userSettings={userSettings}
                    setUserSettings={setUserSettings}
                  />
                </Tabs.Content>
              )}
          </Tabs.Root>
        </Collapsible.Content>
      </Collapsible.Root>
    </Box>
  );
};

export default UserSettingsPanel;
