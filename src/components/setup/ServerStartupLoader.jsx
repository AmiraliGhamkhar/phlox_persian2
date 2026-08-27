import { useState, useEffect, useRef } from "react";
import { Box, Button, Heading, VStack, Text, Flex, Spinner, Icon } from "@chakra-ui/react";
import { FaServer } from "react-icons/fa";
import { settingsApi } from "../../utils/api/settingsApi";
import { isTauri } from "../../utils/helpers/apiConfig";

const LOADING_MESSAGES = [
  "در حال آماده‌سازی زیرساخت...",
  "در حال راه‌اندازی پایگاه داده...",
  "در حال مرتب‌سازی فرایندها...",
  "در حال آماده‌سازی موتور پردازش...",
  "در حال بررسی منابع سیستم...",
  "در حال رمزگشایی داده‌ها...",
  "در حال بررسی وضعیت سرویس‌ها...",
  "در حال هماهنگ‌سازی اجزای اصلی...",
  "در حال آماده‌سازی محیط...",
  "در حال بارگذاری مرحله بعد...",
  "در حال آماده‌سازی مدل‌ها...",
  "در حال بهینه‌سازی حافظه...",
  "در حال اتصال به موتور هوش مصنوعی...",
  "در حال تکمیل آماده‌سازی...",
  "در حال تخصیص حافظه بیشتر...",
];

const POLL_INTERVAL = 2000; // ms - increased to reduce CPU load
const TIMEOUT = 60000; // 60 seconds - increased for slower systems

const ServerStartupLoader = ({ onReady, onError }) => {

  const [messageIndex, setMessageIndex] = useState(0);
  const [isTimedOut, setIsTimedOut] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [shouldPoll, setShouldPoll] = useState(true);

  // Store callbacks and state in refs to avoid dependency issues
  const onReadyRef = useRef(onReady);
  const onErrorRef = useRef(onError);
  const shouldPollRef = useRef(shouldPoll);
  const isTimedOutRef = useRef(isTimedOut);

  // Keep refs in sync with state
  useEffect(() => {
    onReadyRef.current = onReady;
    onErrorRef.current = onError;
    shouldPollRef.current = shouldPoll;
    isTimedOutRef.current = isTimedOut;
  }, [onReady, onError, shouldPoll, isTimedOut]);

  // Single consolidated useEffect for all intervals
  // Note: We track shouldPoll/isTimedOut inside the interval callbacks
  // rather than as dependencies to prevent interval recreation
  useEffect(() => {
    if (!shouldPoll) return;

    let elapsedInterval, pollInterval, messageInterval, timeoutId;

    // Update elapsed time
    elapsedInterval = setInterval(() => {
      setElapsed((prev) => prev + POLL_INTERVAL);
    }, POLL_INTERVAL);

    // Poll server status - inline to avoid dependency issues
    const pollServerStatusAsync = async () => {
      // Check refs instead of state to avoid stale closures
      if (shouldPollRef.current && !isTimedOutRef.current) {
        try {
          await settingsApi.fetchServerStatus(AbortSignal.timeout(5000));
          shouldPollRef.current = false;
          setShouldPoll(false);
          onReadyRef.current();
        } catch {
          // Server not ready yet, continue polling
        }
      }
    };

    // Initial poll
    pollServerStatusAsync();

    // Set up polling interval
    pollInterval = setInterval(pollServerStatusAsync, POLL_INTERVAL);

    // Cycle loading messages every 2 seconds
    messageInterval = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % LOADING_MESSAGES.length);
    }, 2000);

    // Timeout after 30 seconds
    timeoutId = setTimeout(() => {
      shouldPollRef.current = false;
      setShouldPoll(false);
      setIsTimedOut(true);
      onErrorRef.current(new Error("Server startup timed out"));
    }, TIMEOUT);

    // Cleanup ALL intervals
    return () => {
      clearInterval(elapsedInterval);
      clearInterval(pollInterval);
      clearInterval(messageInterval);
      clearTimeout(timeoutId);
    };
     
  }, [shouldPoll]);

  const handleRetry = () => {
    setIsTimedOut(false);
    setElapsed(0);
    setShouldPoll(true);
  };

  if (isTimedOut) {
    return (
      <Flex
        align="center"
        justify="center"
        minH="100dvh"
        className="splash-bg"
        px={4}
        py={8}
        position="relative"
      >
        {/* Tauri titlebar drag region - full window width */}
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
        <Box
          className="anim-fade-slide-up panels-bg splash-panel"
          p={8}
          borderRadius="2xl"
          boxShadow="2xl"
          border={`1px solid ${"surface"}`}
          w="100%"
          maxW="450px"
          textAlign="center"
        >
          <VStack gap={6}>
            <Icon boxSize={12} color="dangerButton" asChild><FaServer /></Icon>
            <Heading
              as="h1"
              color={"textPrimary"}
              css={{
                fontFamily: '"Space Grotesk", sans-serif',
                fontSize: "1.5rem",
                fontWeight: "700"
              }}
            >
              راه‌اندازی سرور بیش از حد طول کشید
            </Heading>
            <Text color={"textSecondary"}>
              راه‌اندازی سرور بیشتر از زمان معمول طول کشیده است. ممکن است منابع
              سیستم یا عوامل دیگری باعث این تأخیر شده باشند.
            </Text>
            <Text color={"textSecondary"} fontSize="sm">
              مدت انتظار: {Math.floor(elapsed / 1000)} ثانیه
            </Text>
            <Button
              onClick={handleRetry}
              size="lg"
              className="green-button"
              css={{
                fontFamily: '"Space Grotesk", sans-serif',
                fontWeight: "600"
              }}
            >
              تلاش دوباره
            </Button>
          </VStack>
        </Box>
      </Flex>
    );
  }

  return (
    <Flex
      align="center"
      justify="center"
      minH="100dvh"
      className="splash-bg"
      px={4}
      py={8}
      position="relative"
    >
      {/* Tauri titlebar drag region - full window width */}
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
      <Box
        className="anim-fade-slide-up panels-bg splash-panel"
        p={8}
        borderRadius="2xl"
        boxShadow="2xl"
        border={`1px solid ${"surface"}`}
        w="100%"
        maxW="450px"
        textAlign="center"
      >
        <VStack gap={6}>
          <Spinner
            size="xl"
            color={"accent"}
            borderWidth="4px"
            animationDuration="0.8s"
          />
          <Heading
            as="h1"
            color={"textPrimary"}
            css={{
              fontFamily: '"Space Grotesk", sans-serif',
              fontSize: "1.5rem",
              fontWeight: "700"
            }}
          >
            در حال راه‌اندازی سرور
          </Heading>
          <Text color={"textSecondary"} fontSize="lg" minH="2rem">
            {LOADING_MESSAGES[messageIndex]}
          </Text>
        </VStack>
        </Box>
      </Flex>
  );
};

export default ServerStartupLoader;
