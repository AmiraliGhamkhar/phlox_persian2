import { Alert, Badge, Box, Button, Checkbox, Flex, HStack, IconButton, Input, Spacer, Switch, Text, VStack, Field } from "@chakra-ui/react";
import { Tooltip } from '@/components/ui/tooltip';
import {
    FaPuzzlePiece,
    FaPlus,
    FaCheck,
    FaServer,
    FaLock,
} from "react-icons/fa";
import { DeleteIcon } from "../common/icons";
import { useMemo, useState } from "react";
import { useToolServers } from "../../utils/hooks/useToolServers";

const BUILT_IN_TOOL_GROUPS = [
    {
        title: "جست‌وجو و منابع",
        tools: [
            {
                name: "transcript_search",
                label: "جست‌وجوی متن‌های پیاده‌سازی‌شده",
                description: "جست‌وجوی متن‌های پیاده‌سازی‌شده بیماران",
                external: false,
            },
            {
                name: "get_relevant_literature",
                label: "جست‌وجوی منابع علمی",
                description: "پایگاه داده محلی منابع علمی",
                external: false,
            },
            {
                name: "pubmed_search",
                label: "جست‌وجوی PubMed",
                description: "API پاب‌مد (ممکن است PHI را افشا کند)",
                external: true,
            },
            {
                name: "wiki_search",
                label: "جست‌وجوی ویکی‌پدیا",
                description: "API ویکی‌پدیا (ممکن است PHI را افشا کند)",
                external: true,
            },
        ],
    },
    {
        title: "بیمار و سوابق",
        tools: [
            {
                name: "get_previous_encounter",
                label: "ویزیت‌های قبلی",
                description: "جست‌وجوی سابقه بیمار",
                external: false,
            },
            {
                name: "search_patient",
                label: "جست‌وجوی بیمار",
                description: "جست‌وجو بر اساس نام، شماره پرونده یا تاریخ",
                external: false,
            },
            {
                name: "search_patient_notes",
                label: "جست‌وجوی یادداشت‌های بیمار",
                description: "جست‌وجو در سوابق و یادداشت‌های بیمار",
                external: false,
            },
            {
                name: "search_patients_by_condition",
                label: "جست‌وجوی بیماران بر اساس بیماری",
                description: "فهرست بیماران با یک تشخیص مشابه",
                external: false,
            },
            {
                name: "create_note",
                label: "ایجاد یادداشت",
                description: "ایجاد یادداشت ویزیت جدید (نیاز به تأیید)",
                external: false,
            },
        ],
    },
    {
        title: "کارها",
        tools: [
            {
                name: "get_patient_jobs",
                label: "کارهای بیمار",
                description: "فهرست کارهای ناتمام یک بیمار",
                external: false,
            },
            {
                name: "list_outstanding_jobs",
                label: "همه کارهای ناتمام",
                description: "فهرست کارهای ناتمام همه بیماران",
                external: false,
            },
            {
                name: "complete_job",
                label: "تکمیل کار",
                description: "علامت‌گذاری یک کار به‌عنوان انجام‌شده (نیاز به تأیید)",
                external: false,
            },
            {
                name: "todo_list",
                label: "فهرست کارهای شخصی",
                description: "لیست کارهای سراسری کاربر",
                external: false,
            },
        ],
    },
    {
        title: "فرم‌های PDF",
        tools: [
            {
                name: "list_pdf_form_templates",
                label: "فهرست قالب‌های PDF",
                description: "قالب‌های فرم PDF موجود",
                external: false,
            },
            {
                name: "fill_pdf_form",
                label: "پر کردن فرم PDF",
                description: "پر کردن یک قالب PDF (نیاز به تأیید)",
                external: false,
            },
        ],
    },
];

const ToolsSettingsTab = ({ className }) => {
    const {
        toolServers,
        cachedMcpTools,
        isLoading,
        testingServerId,
        addServer,
        deleteServer,
        toggleServer,
        toggleSensitiveData,
        testServer,
        toggleBuiltInTool,
        toggleMcpTool,
        isToolEnabled,
    } = useToolServers();

    const mcpToolsByServer = useMemo(() => {
        const grouped = {};
        for (const tool of cachedMcpTools || []) {
            const serverId = tool.server_id;
            if (serverId == null) continue;
            if (!grouped[serverId]) grouped[serverId] = [];
            grouped[serverId].push(tool);
        }
        return grouped;
    }, [cachedMcpTools]);

    const [showAddForm, setShowAddForm] = useState(false);
    const [serverName, setServerName] = useState("");
    const [serverUrl, setServerUrl] = useState("");
    const [allowSensitiveData, setAllowSensitiveData] = useState(false);
    const [nameError, setNameError] = useState("");
    const [urlError, setUrlError] = useState("");

    const validateForm = () => {
        let isValid = true;
        setNameError("");
        setUrlError("");

        if (!serverName.trim()) {
            setNameError("نام سرور الزامی است");
            isValid = false;
        }

        if (!serverUrl.trim()) {
            setUrlError("نشانی سرور الزامی است");
            isValid = false;
        } else {
            try {
                new URL(serverUrl);
            } catch {
                setUrlError("لطفاً یک نشانی معتبر وارد کنید");
                isValid = false;
            }
        }

        return isValid;
    };

    const handleAddServer = async () => {
        if (!validateForm()) return;
        const ok = await addServer({
            name: serverName,
            url: serverUrl,
            allow_sensitive_data: allowSensitiveData,
        });
        if (ok) {
            setServerName("");
            setServerUrl("");
            setAllowSensitiveData(false);
            setShowAddForm(false);
        }
    };

    return (
        <VStack gap={4} align="stretch" className={className}>
            {/* Warning Banner */}
            <Alert.Root status="warning" borderRadius="md">
                <Alert.Indicator color="secondaryButton" />
                <Alert.Description fontSize="sm">
                    سرورهای ابزار ممکن است اطلاعات حساس بیمار (PHI) را دریافت کنند.
                    فقط سرورهای مورد اعتماد و سازگار با الزامات حریم خصوصی خود را اضافه کنید.
                </Alert.Description>
            </Alert.Root>
            {/* ابزارهای داخلی Section */}
            <Box>
                <Flex align="center" mb={2}>
                    <HStack>
                        <FaPuzzlePiece style={{ opacity: 0.7 }} />
                        <Text fontSize="sm" fontWeight="semibold">
                            ابزارهای داخلی
                        </Text>
                    </HStack>
                </Flex>

                <Text fontSize="xs" className="pill-box-icons" mb={2}>
                    ابزارهای داخلی را فعال یا غیرفعال کنید. ابزارهای خارجی (PubMed و
                    Wikipedia) برای حفاظت از حریم خصوصی بیمار به‌صورت پیش‌فرض غیرفعال‌اند.
                </Text>

                <VStack gap={3} align="stretch">
                    {BUILT_IN_TOOL_GROUPS.map((group) => (
                        <Box key={group.title}>
                            <Text fontSize="xs" fontWeight="semibold" mb={1}>
                                {group.title}
                            </Text>
                            <VStack gap={1} align="stretch">
                                {group.tools.map((tool) => (
                                    <Box
                                        key={tool.name}
                                        p={2}
                                        borderRadius="md"
                                        className="floating-main"
                                    >
                                        <Flex justify="space-between" align="center">
                                            <HStack gap={2} flex="1">
                                                <Box flex="1">
                                                    <HStack>
                                                        <Text
                                                            fontWeight="medium"
                                                            fontSize="sm"
                                                        >
                                                            {tool.label}
                                                        </Text>
                                                        {tool.external && (
                                                            <Tooltip content="API خارجی — ممکن است PHI را افشا کند">
                                                                <Box>
                                                                    <FaLock
                                                                        style={{
                                                                            opacity: 0.6,
                                                                            color: "var(--chakra-colors-secondary-button)",
                                                                        }}
                                                                    />
                                                                </Box>
                                                            </Tooltip>
                                                        )}
                                                    </HStack>
                                                    <Text
                                                        fontSize="xs"
                                                        className="pill-box-icons"
                                                    >
                                                        {tool.description}
                                                    </Text>
                                                </Box>
                                            </HStack>

                                            <Switch.Root
                                                checked={isToolEnabled(tool.name)}
                                                onCheckedChange={({ checked }) =>
                                                    toggleBuiltInTool(tool.name, checked)
                                                }
                                                size="sm"
                                            >
                                                <Switch.HiddenInput />
                                                <Switch.Control>
                                                    <Switch.Thumb />
                                                </Switch.Control>
                                            </Switch.Root>
                                        </Flex>
                                    </Box>
                                ))}
                            </VStack>
                        </Box>
                    ))}
                </VStack>
            </Box>
            {/* سرورهای ابزار Header */}
            <Flex align="center">
                <HStack>
                    <FaPuzzlePiece style={{ opacity: 0.7 }} />
                    <Text fontSize="sm" fontWeight="semibold">
                        سرورهای ابزار
                    </Text>
                </HStack>
                <Spacer />
                <Badge colorPalette="purple" fontSize="xs">
                    MCP
                </Badge>
            </Flex>
            <Text fontSize="xs" className="pill-box-icons">
                سرورهای ابزار MCP ابزارهای بیشتری برای گفتگو فراهم می‌کنند.
                اتصال ابتدا با Streamable HTTP و در صورت نیاز با SSE انجام می‌شود.
            </Text>
            {/* Add Server Button */}
            <Button
                onClick={() => setShowAddForm(!showAddForm)}
                variant="outline"
                size="sm"
                className="nav-button"
                alignSelf="flex-start"><FaPlus />افزودن سرور
                            </Button>
            {/* Add Server Form */}
            {showAddForm && (
                <Box p={4} borderRadius="md" className="floating-main">
                    <VStack gap={3}>
                        <Field.Root invalid={!!nameError}>
                            <Field.Label fontSize="xs">نام سرور</Field.Label>
                            <Input
                                value={serverName}
                                onChange={(e) => setServerName(e.target.value)}
                                placeholder="سرور MCP من"
                                size="sm"
                                className="input-style"
                            />
                            <Field.ErrorText fontSize="xs">
                                {nameError}
                            </Field.ErrorText>
                        </Field.Root>

                        <Field.Root invalid={!!urlError}>
                            <Field.Label fontSize="xs">نشانی سرور</Field.Label>
                            <Input
                                value={serverUrl}
                                onChange={(e) => setServerUrl(e.target.value)}
                                placeholder="http://localhost:3000/mcp"
                                size="sm"
                                className="input-style"
                            />
                            <Field.ErrorText fontSize="xs">
                                {urlError}
                            </Field.ErrorText>
                        </Field.Root>

                        <Field.Root>
                            <HStack gap={2}>
                                <Checkbox.Root
                                    onCheckedChange={({ checked }) => setAllowSensitiveData(checked)}
                                    colorPalette="red"
                                    size="sm"
                                    checked={allowSensitiveData}
                                ><Checkbox.HiddenInput /><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Checkbox.Label>
                                    <Text fontSize="xs">اجازه ارسال داده‌های حساس (PHI)</Text>
                                </Checkbox.Label></Checkbox.Root>
                                <Tooltip content="در صورت فعال بودن، داده‌های بیمار بدون پاک‌سازی به این سرور ارسال می‌شود. فقط برای سرور کاملاً مورد اعتماد فعال کنید.">
                                    <Box>
                                        <FaLock style={{ opacity: 0.6, color: "var(--chakra-colors-secondary-button)" }} />
                                    </Box>
                                </Tooltip>
                            </HStack>
                            <Text fontSize="xs" className="pill-box-icons" mt={1}>
                                Default: sanitized. فعال‌سازی only for trusted servers.
                            </Text>
                        </Field.Root>

                        <HStack justify="flex-end" w="100%">
                            <Button
                                onClick={() => setShowAddForm(false)}
                                variant="ghost"
                                size="sm"
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={handleAddServer}
                                loading={isLoading}
                                colorPalette="green"
                                size="sm"
                            >
                                Add Server
                            </Button>
                        </HStack>
                    </VStack>
                </Box>
            )}
            {/* Server List */}
            {toolServers.length === 0 ? (
                <Box p={6} textAlign="center" className="floating-main">
                    <FaServer
                        size="1.5em"
                        style={{ opacity: 0.5, marginBottom: "8px" }}
                    />
                    <Text fontSize="sm" className="pill-box-icons">
                        No tool servers configured
                    </Text>
                    <Text fontSize="xs" className="pill-box-icons" mt={1}>
                        Add a server to extend available tools
                    </Text>
                </Box>
            ) : (
                <VStack gap={2} align="stretch">
                    {toolServers.map((server) => (
                        <Box
                            key={server.id}
                            p={3}
                            borderRadius="md"
                            className="floating-main"
                        >
                            <Flex justify="space-between" align="center">
                                <HStack gap={3} flex="1">
                                    <FaServer style={{ opacity: 0.5 }} />
                                    <Box flex="1">
                                        <HStack>
                                            <Text
                                                fontWeight="bold"
                                                fontSize="sm"
                                            >
                                                {server.name}
                                            </Text>
                                            <Badge
                                                size="sm"
                                                colorPalette={
                                                    server.enabled
                                                        ? "green"
                                                        : "gray"
                                                }
                                                fontSize="xs"
                                            >
                                                {server.enabled
                                                    ? "فعال"
                                                    : "غیرفعال"}
                                            </Badge>
                                            {server.allow_sensitive_data && (
                                                <Tooltip content="PHI مجاز است — داده‌ها بدون پاک‌سازی ارسال می‌شوند">
                                                    <Badge
                                                        size="sm"
                                                        colorPalette="red"
                                                        fontSize="xs"
                                                    >
                                                        PHI
                                                    </Badge>
                                                </Tooltip>
                                            )}
                                        </HStack>
                                        <Text
                                            fontSize="xs"
                                            className="pill-box-icons"
                                        >
                                            {server.url}
                                        </Text>
                                        {server.description && (
                                            <Text
                                                fontSize="xs"
                                                className="pill-box-icons"
                                                fontStyle="italic"
                                                opacity={0.8}
                                            >
                                                {server.description}
                                            </Text>
                                        )}
                                    </Box>
                                </HStack>

                                <HStack gap={1}>
                                    <Tooltip content="آزمایش اتصال">
                                        <IconButton
                                            size="sm"
                                            variant="ghost"
                                            onClick={() =>
                                                testServer(server.id)
                                            }
                                            loading={
                                                testingServerId === server.id
                                            }
                                            aria-label="آزمایش اتصال"><FaCheck /></IconButton>
                                    </Tooltip>

                                    <Tooltip
                                        content={
                                            server.allow_sensitive_data
                                                ? "PHI مجاز است — برای پاک‌سازی کلیک کنید"
                                                : "PHI پاک‌سازی شده است — برای اجازه ارسال کلیک کنید"
                                        }
                                    >
                                        <IconButton
                                            size="sm"
                                            variant="ghost"
                                            colorPalette={server.allow_sensitive_data ? "red" : "gray"}
                                            opacity={server.allow_sensitive_data ? 1 : 0.4}
                                            onClick={() =>
                                                toggleSensitiveData(
                                                    server.id,
                                                    !server.allow_sensitive_data,
                                                )
                                            }
                                            aria-label="تغییر وضعیت پاک‌سازی PHI"><FaLock /></IconButton>
                                    </Tooltip>

                                    <Tooltip
                                        content={
                                            server.enabled
                                                ? "غیرفعال‌سازی"
                                                : "فعال‌سازی"
                                        }
                                    >
                                        <Switch.Root
                                            checked={server.enabled}
                                            onCheckedChange={({ checked }) =>
                                                toggleServer(server.id, checked)
                                            }
                                            size="sm"
                                        >
                                            <Switch.HiddenInput />
                                            <Switch.Control>
                                                <Switch.Thumb />
                                            </Switch.Control>
                                        </Switch.Root>
                                    </Tooltip>

                                    <Tooltip content="حذف">
                                        <IconButton
                                            size="sm"
                                            colorPalette="red"
                                            variant="ghost"
                                            onClick={() =>
                                                deleteServer(server.id)
                                            }
                                            aria-label="حذف سرور"><DeleteIcon /></IconButton>
                                    </Tooltip>
                                </HStack>
                            </Flex>
                            {(mcpToolsByServer[server.id] || []).length > 0 ? (
                                <VStack align="stretch" gap={1} mt={2}>
                                    <Text fontSize="xs" className="pill-box-icons">
                                        ابزارهای این سرور
                                    </Text>
                                    {mcpToolsByServer[server.id].map((tool) => {
                                        const toolName = tool.server_tool_name || tool.name;
                                        const disabledSet = new Set(
                                            server.disabled_tools || [],
                                        );
                                        const enabled = !disabledSet.has(toolName);
                                        return (
                                            <Flex
                                                key={toolName}
                                                justify="space-between"
                                                align="center"
                                                px={1}
                                            >
                                                <Box flex="1" minW={0}>
                                                    <Text fontSize="xs" fontWeight="medium">
                                                        {toolName}
                                                    </Text>
                                                    {tool.description && (
                                                        <Text
                                                            fontSize="xs"
                                                            className="pill-box-icons"
                                                            lineClamp={2}
                                                        >
                                                            {tool.description}
                                                        </Text>
                                                    )}
                                                </Box>
                                                <Switch.Root
                                                    checked={enabled}
                                                    onCheckedChange={({ checked }) =>
                                                        toggleMcpTool(
                                                            server.id,
                                                            toolName,
                                                            checked,
                                                        )
                                                    }
                                                    size="sm"
                                                >
                                                    <Switch.HiddenInput />
                                                    <Switch.Control>
                                                        <Switch.Thumb />
                                                    </Switch.Control>
                                                </Switch.Root>
                                            </Flex>
                                        );
                                    })}
                                </VStack>
                            ) : (
                                <Text fontSize="xs" className="pill-box-icons" mt={2}>
                                    برای فهرست ابزارها، اتصال را آزمایش کنید.
                                </Text>
                            )}
                        </Box>
                    ))}
                </VStack>
            )}
        </VStack>
    );
};

export default ToolsSettingsTab;
