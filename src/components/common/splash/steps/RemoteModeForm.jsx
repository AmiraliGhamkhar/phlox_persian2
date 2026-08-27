import {
  VStack,
  HStack,
  Text,
  Input,
  NativeSelect,
  Field,
  Spinner,
} from "@chakra-ui/react";
import { Tooltip } from "@/components/ui/tooltip";
import { InfoIcon } from "../../icons";

export const RemoteModeForm = ({
  llmBaseUrl,
  setLlmBaseUrl,
  llmApiKey,
  setLlmApiKey,
  primaryModel,
  setPrimaryModel,
  availableModels,
  isFetchingLLMModels,
  whisperBaseUrl,
  setWhisperBaseUrl,
  whisperModel,
  setWhisperModel,
  asrLanguage,
  setAsrLanguage,
  asrProvider,
  setAsrProvider,
  asrApiKey,
  setAsrApiKey,
  availableWhisperModels,
  whisperModelListAvailable,
  isFetchingWhisperModels,
}) => {
  return (
    <VStack gap={3} w="100%">
      <Field.Root>
        <HStack>
          <Field.Label fontSize="sm" color="textSecondary">
            API URL
          </Field.Label>
          <Tooltip
            content="نقطه پایانی سازگار با OpenAI/Ollama؛ معمولاً برای Ollama از نشانی سرویس استفاده می‌شود."
            showArrow
          >
            <InfoIcon boxSize={3} color="textSecondary" />
          </Tooltip>
        </HStack>
        <Input
          placeholder="https://api.example.com"
          value={llmBaseUrl}
          onChange={(e) => setLlmBaseUrl(e.target.value)}
          className="input-style"
          size="sm"
        />
      </Field.Root>

      <Field.Root>
        <HStack>
          <Field.Label fontSize="sm" color="textSecondary">
            API Key
          </Field.Label>
          <Tooltip
            content="کلید API برای احراز هویت سرویس؛ برای سرویس‌های محلی بدون احراز هویت خالی بگذارید."
            showArrow
          >
            <InfoIcon boxSize={3} color="textSecondary" />
          </Tooltip>
        </HStack>
        <Input
          type="password"
          placeholder="کلید API، در صورت نیاز"
          value={llmApiKey}
          onChange={(e) => setLlmApiKey(e.target.value)}
          className="input-style"
          size="sm"
        />
      </Field.Root>

      <Field.Root required={availableModels.length > 0}>
        <HStack>
          <Field.Label fontSize="sm" color="textSecondary">
            مدل اصلی
          </Field.Label>
          <Tooltip
            content="مدل اصلی هوش مصنوعی برای پرسش‌های پزشکی؛ llama3.1:8b یا gpt-4 پیشنهاد می‌شود."
            showArrow
          >
            <InfoIcon boxSize={3} color="textSecondary" />
          </Tooltip>
        </HStack>
        <NativeSelect.Root>
          <NativeSelect.Field
            placeholder={
              availableModels.length === 0 && !isFetchingLLMModels
                ? "مدلی پیدا نشد — نشانی را بررسی کنید"
                : "انتخاب مدل"
            }
            value={primaryModel}
            onChange={(e) => setPrimaryModel(e.target.value)}
            disabled={isFetchingLLMModels || availableModels.length === 0}
            className="input-style"
            size="sm"
          >
            {availableModels.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </NativeSelect.Field>
          <NativeSelect.Indicator />
        </NativeSelect.Root>
        {isFetchingLLMModels && (
          <HStack gap={2} mt={2}>
            <Spinner size="xs" color="primaryButton" />
            <Text fontSize="sm" color="textSecondary">
              در حال دریافت مدل‌ها...
            </Text>
          </HStack>
        )}
      </Field.Root>

      {/* Transcription settings — always visible */}
      <VStack gap={2} w="100%" align="stretch">
        <Text fontSize="xs" fontWeight="bold" className="pill-box-icons">
          تشخیص گفتار (ASR)
        </Text>
        <Field.Root>
          <Field.Label fontSize="sm" color="textSecondary">
            ارائه‌دهنده ASR
          </Field.Label>
          <NativeSelect.Root>
            <NativeSelect.Field
              value={asrProvider}
              onChange={(e) => setAsrProvider(e.target.value)}
              className="input-style"
              size="sm"
            >
              <option value="openai_compatible">سرویس سازگار با OpenAI</option>
              <option value="speechmatics">Speechmatics؛ بلادرنگ</option>
            </NativeSelect.Field>
            <NativeSelect.Indicator />
          </NativeSelect.Root>
        </Field.Root>
        <Field.Root>
          <Field.Label fontSize="sm" color="textSecondary">
            زبان گفتار
          </Field.Label>
          <NativeSelect.Root>
            <NativeSelect.Field
              value={asrLanguage}
              onChange={(e) => setAsrLanguage(e.target.value)}
              className="input-style"
              size="sm"
            >
              <option value="auto">تشخیص خودکار (فارسی و انگلیسی ترکیبی)</option>
              <option value="fa">فارسی</option>
              <option value="en">انگلیسی</option>
            </NativeSelect.Field>
            <NativeSelect.Indicator />
          </NativeSelect.Root>
        </Field.Root>

        {asrProvider === "openai_compatible" && (
          <Field.Root>
            <Field.Label fontSize="sm" color="textSecondary">
              نشانی سرویس ASR
            </Field.Label>
            <Input
              type="url"
              data-ltr="true"
              placeholder="https://asr.example.com"
              value={whisperBaseUrl}
              onChange={(e) => setWhisperBaseUrl(e.target.value)}
              className="input-style"
              size="sm"
            />
          </Field.Root>
        )}
        {asrProvider === "speechmatics" && (
          <Field.Root>
            <Field.Label fontSize="sm" color="textSecondary">
              کلید API سرویس Speechmatics
            </Field.Label>
            <Input
              type="password"
              placeholder="کلید در این دستگاه ذخیره می‌شود"
              value={asrApiKey}
              onChange={(e) => setAsrApiKey(e.target.value)}
              className="input-style"
              size="sm"
            />
          </Field.Root>
        )}
        {(asrProvider === "speechmatics" || whisperBaseUrl.trim()) && (
          <Field.Root>
            <Field.Label fontSize="sm" color="textSecondary">
              مدل ASR
            </Field.Label>
            {asrProvider === "speechmatics" ? (
              <NativeSelect.Root>
                <NativeSelect.Field
                  value={whisperModel || "enhanced"}
                  onChange={(e) => setWhisperModel(e.target.value)}
                  className="input-style"
                  size="sm"
                >
                  <option value="enhanced">حالت پیشرفته؛ دقت بالاتر</option>
                  <option value="standard">حالت استاندارد؛ سرعت بالاتر</option>
                </NativeSelect.Field>
                <NativeSelect.Indicator />
              </NativeSelect.Root>
            ) : whisperModelListAvailable && availableWhisperModels.length > 0 ? (
              <NativeSelect.Root>
                <NativeSelect.Field
                  placeholder="انتخاب مدل"
                  value={whisperModel}
                  onChange={(e) => setWhisperModel(e.target.value)}
                  disabled={isFetchingWhisperModels}
                  className="input-style"
                  size="sm"
                >
                  {availableWhisperModels.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </NativeSelect.Field>
                <NativeSelect.Indicator />
              </NativeSelect.Root>
            ) : (
              <Input
                placeholder="مثلاً whisper-1، base یا small"
                value={whisperModel}
                onChange={(e) => setWhisperModel(e.target.value)}
                disabled={isFetchingWhisperModels}
                className="input-style"
                size="sm"
              />
            )}
            {isFetchingWhisperModels && (
              <HStack gap={2} mt={2}>
                <Spinner size="xs" color="primaryButton" />
                <Text fontSize="sm" color="textSecondary">
                  در حال بارگذاری...
                </Text>
              </HStack>
            )}
          </Field.Root>
        )}
      </VStack>
    </VStack>
  );
};
