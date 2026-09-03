import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
} from "react";
import TextareaAutosize from "react-textarea-autosize";
import { Box, Flex, Text, Collapsible, HStack, NativeSelect, VStack, Center, Spinner } from "@chakra-ui/react";
import { toaster } from "@/components/ui/toaster";
import { Tooltip } from '@/components/ui/tooltip';
import {
  EditIcon,
  CopyIcon,
  CheckIcon,
} from "../common/icons";
import { FaSave, FaFileAlt, FaThumbtack, FaCheckDouble } from "react-icons/fa";
import { GreenButton, GreyButton } from "../common/Buttons";
import { useTemplateSelection } from "../../utils/templates/templateContext";
import { patientApi } from "../../utils/api/patientApi";
import ConfirmLeaveModal from "../modals/ConfirmLeaveModal";

const Summary = forwardRef(
  (
    {
      isSummaryCollapsed,
      patient,
      setPatient,
      handleGenerateLetterClick,
      handleSavePatientData,
      saveLoading,
      onWrapUp,
      wrapUpLoading,
      setIsModified,
      onCopy,
      recentlyCopied,
      isNewPatient,
      selectTemplate,
      isSearchedPatient,
      isEncounterSaved = false,
      asrVerification = null,
      asrDraftFields = null,
    },
    ref,
  ) => {
    const {
      currentTemplate,
      templates,
      status: templateStatus,
    } = useTemplateSelection();

    const textareasRefs = useRef({});
    const [showDraft, setShowDraft] = useState(false);

    // Verification findings mapped per field (plan ref D1). These are review
    // hints from the deterministic guards and the independent entailment
    // pass — the text itself is always left editable.
    const fieldIssues = {};
    const pushIssue = (key, label, text) => {
      if (!key) return;
      (fieldIssues[key] = fieldIssues[key] || []).push({ label, text });
    };
    if (asrVerification) {
      (asrVerification.unsupportedQuotes || []).forEach((v) =>
        pushIssue(v.field, "خارج از متن", v.point || ""),
      );
      (asrVerification.numberProblems || []).forEach((v) =>
        pushIssue(v.field, "عدد تایید نشده", `${v.value}${v.point ? ` — ${v.point}` : ""}`),
      );
      (asrVerification.negationProblems || []).forEach((v) =>
        pushIssue(v.field, "تضاد نفی", v.point || v.transcriptClause || ""),
      );
      (asrVerification.refinementReverts || []).forEach((v) =>
        pushIssue(v.field, "بازگردش ویرایش", (v.drift || []).join("، ")),
      );
      ((asrVerification.entailment && asrVerification.entailment.flaggedClaims) || []).forEach(
        (v) =>
          pushIssue(
            v.field,
            "بدون پشتوانه (بررسی مستقل)",
            v.evidence ? `${v.claim} — ${v.evidence}` : v.claim || "",
          ),
      );
    }
    const totalIssues = Object.values(fieldIssues).reduce((n, l) => n + l.length, 0);
    const hasDraft =
      Boolean(asrDraftFields) &&
      Object.keys(asrDraftFields || {}).some(
        (k) => asrDraftFields[k] && asrDraftFields[k] !== patient?.template_data?.[k],
      );
    const [isTemplateChangeModalOpen, setIsTemplateChangeModalOpen] =
      useState(false);
    const [pendingTemplateKey, setPendingTemplateKey] = useState(null);

    const handleTemplateChange = async (e) => {
      const newTemplateKey = e.target.value;

      if (!isNewPatient && !isSearchedPatient) {
        toaster.create({
          title: "قالب قفل است",
          description: "قالب ویزیت‌های تاریخی قابل تغییر نیست",
          type: "warning",
          duration: 3000,
        });
        return;
      }

      setPendingTemplateKey(newTemplateKey);
      setIsTemplateChangeModalOpen(true);
    };

    const confirmTemplateChange = async () => {
      console.log("confirmTemplateChange called", {
        ur_number: patient?.ur_number,
        pendingTemplateKey,
      });

      // If patient has a UR number, fetch persistent fields for the new template type
      if (patient?.ur_number) {
        try {
          // Extract base template key (e.g., "soap" from "soap_01")
          const baseTemplateKey = pendingTemplateKey.split("_")[0];
          console.log("Fetching history for template:", baseTemplateKey);

          const history = await patientApi.fetchPatientHistoryByTemplate(
            patient.ur_number,
            baseTemplateKey,
          );

          console.log("History result:", history);

          if (history && history.length > 0) {
            // Merge persistent fields from most recent note of this type
            const mostRecent = history[0];
            setPatient((prev) => ({
              ...prev,
              template_key: pendingTemplateKey,
              template_data: {
                ...mostRecent.template_data,
              },
            }));
            setIsTemplateChangeModalOpen(false);
            await selectTemplate(pendingTemplateKey);
            return;
          }
        } catch (error) {
          console.error("Error fetching history for template:", error);
        }
      }

      // Fallback: just change template without pre-filling
      console.log("Falling back to simple template change");
      selectTemplate(pendingTemplateKey);
      setIsTemplateChangeModalOpen(false);
    };

    const handleTemplateDataChange = (fieldKey, value) => {
      setPatient((prev) => ({
        ...prev,
        template_data: {
          ...prev.template_data,
          [fieldKey]: value,
        },
      }));
      setIsModified(true);
    };

    const renderField = (field) => {
      const persistentMarker = field.persistent ? (
        <Tooltip
          content="بین ویزیت‌ها حفظ می‌شود."
          showArrow
          positioning={{
            placement: "right"
          }}
        >
          <Box as="span" className="cohesive-persistent-marker">
            <FaThumbtack />
          </Box>
        </Tooltip>
      ) : null;

      const issues = fieldIssues[field.field_key] || [];
      const draftValue = asrDraftFields?.[field.field_key];
      const showingDraft = showDraft && Boolean(draftValue);

      return (
        <Box key={field.field_key} className="cohesive-field">
          <Text className="cohesive-field-label">
            {field.field_name}:{persistentMarker}
            {showingDraft ? " (پیش‌نویس)" : ""}
          </Text>
          {issues.length > 0 && !showingDraft && (
            <HStack gap={1.5} mb={1} flexWrap="wrap">
              {issues.map((issue, idx) => (
                <Tooltip
                  key={`${field.field_key}-issue-${idx}`}
                  content={issue.text || issue.label}
                  positioning={{ placement: "top" }}
                >
                  <Box
                    as="span"
                    fontSize="9px"
                    px={1.5}
                    py={0.5}
                    borderRadius="full"
                    bg="rgba(214, 158, 46, 0.12)"
                    color="#B7791F"
                    dir="auto"
                  >
                    {issue.label}
                  </Box>
                </Tooltip>
              ))}
            </HStack>
          )}
          <TextareaAutosize
            placeholder="متن را وارد کنید..."
            value={
              showingDraft
                ? draftValue
                : patient.template_data?.[field.field_key] || ""
            }
            readOnly={showingDraft}
            onChange={(e) => {
              handleTemplateDataChange(field.field_key, e.target.value);
            }}
            className="cohesive-textarea"
            style={showingDraft ? { opacity: 0.75, fontStyle: "italic" } : undefined}
            ref={(el) => (textareasRefs.current[field.field_key] = el)}
          />
        </Box>
      );
    };

    useImperativeHandle(ref, () => ({
      resizeTextarea: () => {
        Object.values(textareasRefs.current).forEach((textarea) => {
          if (textarea) {
            textarea.style.height = "auto";
            textarea.style.height = `${textarea.scrollHeight}px`;
          }
        });
      },
    }));

    if (templateStatus === "loading") {
      return (
        <Box p="4" borderRadius="sm" className="panels-bg">
          <Center mt={4}>
            <Spinner size="sm" animationDuration="0.65s" />
            <Text ml={2}>در حال بارگذاری قالب...</Text>
          </Center>
        </Box>
      );
    }

    return (
      <>
        <Box p={[2, 3, 4]} borderRadius="sm" className="panels-bg">
          <Flex align="center" justify="space-between">
            <Flex align="center">
              <HStack gap={2}>
                <EditIcon size="1.2em" />
                <Text as="h3">یادداشت</Text>
                {totalIssues > 0 && (
                  <Tooltip
                    content="موارد شناسایی‌شده در بازبینی خودکار؛ متن دست‌نخورده و قابل ویرایش است"
                    positioning={{ placement: "bottom" }}
                  >
                    <Box
                      as="span"
                      fontSize="10px"
                      px={2}
                      py={0.5}
                      borderRadius="full"
                      bg="rgba(214, 158, 46, 0.14)"
                      color="#B7791F"
                      border="1px solid rgba(214, 158, 46, 0.4)"
                    >
                      {`${totalIssues} نکته نیازمند بازبینی`}
                    </Box>
                  </Tooltip>
                )}
                {hasDraft && (
                  <Box
                    as="button"
                    type="button"
                    fontSize="10px"
                    px={2}
                    py={0.5}
                    borderRadius="full"
                    border="1px solid var(--chakra-colors-border-translucent)"
                    color="overlay0"
                    cursor="pointer"
                    onClick={() => setShowDraft((v) => !v)}
                  >
                    {showDraft ? "نمایش متن نهایی" : "نمایش پیش‌نویس"}
                  </Box>
                )}
              </HStack>
            </Flex>
            <Tooltip
              content={
                isNewPatient
                  ? "انتخاب قالب"
                  : "قالب ویزیت‌های تاریخی قابل تغییر نیست"
              }
              aria-label="انتخاب قالب یادداشت"
            >
              <Box>
                <Flex alignItems="center">
                  <FaFileAlt
                    style={{ marginRight: "8px" }}
                    className="pill-box-icons"
                  />
                  <NativeSelect.Root>
                    <NativeSelect.Field
                      placeholder="انتخاب قالب"
                      value={
                        currentTemplate?.template_key ||
                        patient?.template_key ||
                        ""
                      }
                      onChange={handleTemplateChange}
                      size="sm"
                      width={["100px", "150px", "200px"]}
                      className="input-style"
                      disabled={!isNewPatient}>
                      {/* Show "قالب تاریخی" only for viewing historical encounters */}
                      {!isNewPatient &&
                        !isSearchedPatient &&
                        patient?.template_key &&
                        !templates?.some(
                          (t) => t.template_key === patient.template_key,
                        ) && (
                          <option value={patient.template_key}>
                            قالب تاریخی
                          </option>
                        )}
                      {templates?.map((t) => (
                        <option key={t.template_key} value={t.template_key}>
                          {t.template_name}
                        </option>
                      ))}
                    </NativeSelect.Field>
                    <NativeSelect.Indicator />
                  </NativeSelect.Root>
                </Flex>
              </Box>
            </Tooltip>
          </Flex>

          <Collapsible.Root open={!isSummaryCollapsed}>
            <Collapsible.Content>
              <Box mt="4" className="cohesive-fields-container">
                <VStack gap="0" align="stretch">
                  {currentTemplate?.fields?.map(renderField)}
                </VStack>
              </Box>
              <Flex mt="4" justifyContent="space-between">
                <Flex>
                  <Tooltip
                    content={
                      isEncounterSaved
                        ? "تولید نامه از این یادداشت"
                        : "برای تولید نامه، ابتدا ویزیت را ذخیره کنید"
                    }
                    positioning={{
                      placement: "top"
                    }}
                  >
                    <Box>
                      <GreyButton
                        onClick={() => handleGenerateLetterClick(null)}
                        leftIcon={<EditIcon />}
                        mr="2"
                        disabled={saveLoading || !isEncounterSaved}
                      >
                        Generate Letter
                      </GreyButton>
                    </Box>
                  </Tooltip>
                </Flex>
                <Flex>
                  <Tooltip
                    content="کپی کل یادداشت در کلیپ‌بورد"
                    positioning={{
                      placement: "top"
                    }}
                  >
                    <Box>
                      <GreyButton
                        onClick={onCopy}
                        width="190px"
                        leftIcon={recentlyCopied ? <CheckIcon /> : <CopyIcon />}
                        mr="2"
                      >
                        {recentlyCopied ? "کپی شد!" : "کپی در کلیپ‌بورد"}
                      </GreyButton>
                    </Box>
                  </Tooltip>
                  <Tooltip
                    content="ذخیره ویزیت فعلی"
                    positioning={{
                      placement: "top"
                    }}
                  >
                    <Box>
                      <GreyButton
                        onClick={handleSavePatientData}
                        loading={saveLoading}
                        loadingText="در حال ذخیره..."
                        width="190px"
                        leftIcon={saveLoading ? null : <FaSave />}
                      >
                        {saveLoading ? "در حال ذخیره..." : "ذخیره ویزیت"}
                      </GreyButton>
                    </Box>
                  </Tooltip>
                  <Tooltip
                    content="کارهای استخراج‌شده توسط هوش مصنوعی را بررسی کنید، سپس پایان دهید و به یادداشت جدید بروید"
                    positioning={{
                      placement: "top"
                    }}
                  >
                    <Box>
                      <GreenButton
                        onClick={onWrapUp}
                        loading={wrapUpLoading}
                        loadingText="در حال جمع‌بندی..."
                        width="150px"
                        ml="2"
                        leftIcon={wrapUpLoading ? null : <FaCheckDouble />}
                        disabled={saveLoading}
                      >
                        {wrapUpLoading ? "در حال جمع‌بندی..." : "جمع‌بندی"}
                      </GreenButton>
                    </Box>
                  </Tooltip>
                </Flex>
              </Flex>
            </Collapsible.Content>
          </Collapsible.Root>
        </Box>
        <ConfirmLeaveModal
          isOpen={isTemplateChangeModalOpen}
          onClose={() => setIsTemplateChangeModalOpen(false)}
          confirmNavigation={confirmTemplateChange}
        />
      </>
    );
  },
);

export default Summary;
