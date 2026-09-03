import { Box, Text, NativeSelect, VStack, HStack, Spinner, Button, Dialog, Portal, Input } from "@chakra-ui/react";
import { Tooltip } from "@/components/ui/tooltip";
import { ReEmbedProgress } from "../common/ReEmbedProgress";
import { useState } from "react";
import { applyEmbeddingProviderDefaults, embeddingProviderIdForLlm } from "../../utils/aiProviders";

const RagTab = ({
    config,
    embeddingModelOptions = [],
    llmModelsLoading = false,
    handleReEmbed,
    handleConfigChange,
    embeddingProviders = [],
}) => {
    const [isEmbeddingModelModalOpen, setIsEmbeddingModelModalOpen] =
        useState(false);
    const [pendingEmbeddingModel, setPendingEmbeddingModel] = useState(null);
    const [isReEmbedding, setIsReEmbedding] = useState(false);
    const [reEmbedProgress, setReEmbedProgress] = useState(null);

    const handleEmbeddingModelChange = (value) => {
        setPendingEmbeddingModel(value);
        setIsEmbeddingModelModalOpen(true);
    };

    const handleConfirmEmbeddingChange = async () => {
        setIsReEmbedding(true);
        setReEmbedProgress({ percentage: 0 });
        try {
            await handleReEmbed(pendingEmbeddingModel, (event) => {
                if (
                    event.type === "batch_progress" ||
                    event.type === "collection_start"
                ) {
                    setReEmbedProgress({
                        percentage: event.percentage ?? 0,
                        collection_index: event.collection_index ?? 0,
                        total_collections: event.total_collections ?? 0,
                        collection_name: event.collection_name ?? "",
                        chunks_embedded: event.chunks_embedded ?? 0,
                        total_chunks_in_collection:
                            event.total_chunks_in_collection ?? 0,
                    });
                }
            });
            setIsEmbeddingModelModalOpen(false);
            setPendingEmbeddingModel(null);
        } catch (error) {
            console.error("Error changing embedding model:", error);
        } finally {
            setIsReEmbedding(false);
            setReEmbedProgress(null);
        }
    };

    const handleCancelEmbeddingChange = () => {
        setIsEmbeddingModelModalOpen(false);
        setPendingEmbeddingModel(null);
    };

    return (
        <>
            <VStack gap={4} align="stretch">
                <Box>
                    <Text fontSize="md" fontWeight="bold">
                        پایگاه دانش (RAG)
                    </Text>
                    <Text fontSize="sm" color="overlay0">
                        مدل بردارسازی استفاده‌شده برای جست‌وجوهای پایگاه دانش را
                        پیکربندی کنید.
                    </Text>
                </Box>

                <Box>
                    <Text fontSize="sm" mb="1" fontWeight="bold">
                        ارائه‌دهنده بردارسازی
                    </Text>
                    <NativeSelect.Root>
                        <NativeSelect.Field
                            size="sm"
                            value={
                                config?.EMBEDDING_PROVIDER ||
                                embeddingProviderIdForLlm(config?.LLM_PROVIDER)
                            }
                            onChange={(event) =>
                                applyEmbeddingProviderDefaults(
                                    event.target.value,
                                    handleConfigChange,
                                )
                            }
                            className="input-style"
                        >
                            {(embeddingProviders.length
                                ? embeddingProviders
                                : [
                                      { id: "local", name: "Local embedding server" },
                                      { id: "ollama", name: "Ollama embeddings" },
                                      { id: "lmstudio", name: "LM Studio embeddings" },
                                      { id: "llamacpp", name: "llama.cpp embeddings" },
                                      { id: "openai", name: "OpenAI embeddings" },
                                      { id: "ninerouter", name: "9Router embeddings" },
                                      { id: "omniroute", name: "OmniRoute embeddings" },
                                      { id: "fireworks", name: "Fireworks embeddings" },
                                      { id: "openai_compatible", name: "Custom OpenAI-compatible" },
                                  ]
                            ).map((item) => (
                                <option key={item.id} value={item.id}>
                                    {item.name_fa || item.name}
                                </option>
                            ))}
                        </NativeSelect.Field>
                        <NativeSelect.Indicator />
                    </NativeSelect.Root>
                    <Text fontSize="xs" color="overlay0" mt="1">
                        بردارسازی مستقل از مدل زبانی پیکربندی می‌شود.
                    </Text>
                </Box>

                {config?.EMBEDDING_PROVIDER !== "local" && (
                    <Box>
                        <Text fontSize="sm" mb="1" fontWeight="bold">
                            نشانی پایه بردارسازی
                        </Text>
                        <Input
                            size="sm"
                            dir="ltr"
                            data-ltr="true"
                            value={config?.EMBEDDING_BASE_URL || ""}
                            onChange={(event) =>
                                handleConfigChange("EMBEDDING_BASE_URL", event.target.value)
                            }
                            placeholder="https://api.example.com"
                            className="input-style"
                        />
                    </Box>
                )}

                <Box>
                    <Tooltip content="مدل تولیدکننده بردارهای RAG؛ تغییر آن همه اسناد را دوباره بردارسازی می‌کند">
                        <Text fontSize="sm" mb="2" fontWeight={"bold"}>
                            مدل بردارسازی
                        </Text>
                    </Tooltip>
                    {llmModelsLoading ? (
                        <HStack gap="2">
                            <Spinner size="sm" />
                            <Text fontSize="sm" color="overlay0">
                                در حال بارگذاری مدل‌ها...
                            </Text>
                        </HStack>
                    ) : embeddingModelOptions.length > 0 ? (
                        <NativeSelect.Root>
                            <NativeSelect.Field
                                size="sm"
                                value={config?.EMBEDDING_MODEL || ""}
                                onChange={(e) =>
                                    handleEmbeddingModelChange(e.target.value)
                                }
                                placeholder="مدل بردارسازی را انتخاب کنید"
                                className="input-style"
                            >
                                {embeddingModelOptions.map((model) => (
                                    <option key={model} value={model}>
                                        {model}
                                    </option>
                                ))}
                            </NativeSelect.Field>
                            <NativeSelect.Indicator />
                        </NativeSelect.Root>
                    ) : (
                        <Input
                            size="sm"
                            dir="ltr"
                            data-ltr="true"
                            placeholder="nomic-embed-text"
                            value={config?.EMBEDDING_MODEL || ""}
                            onChange={(e) =>
                                handleEmbeddingModelChange(e.target.value)
                            }
                            className="input-style"
                        />
                    )}
                    <Text fontSize="xs" color="overlay0" mt="1">
                        فهرست مدل‌ها از ارائه‌دهنده بردارسازی انتخاب‌شده خوانده می‌شود.
                    </Text>
                    <Text
                        fontSize="xs"
                        color="secondaryButton"
                        mt="2"
                        fontWeight="medium"
                    >
                        ⚠️ با تغییر مدل بردارسازی، همه اسناد به‌صورت خودکار
                        دوباره بردارسازی می‌شوند
                    </Text>
                </Box>
            </VStack>

            <Dialog.Root
                open={isEmbeddingModelModalOpen}
                closeOnInteractOutside={!isReEmbedding}
                closeOnEscape={!isReEmbedding}
                size="md"
                onOpenChange={(e) => {
                    if (!e.open) {
                        (
                            isReEmbedding
                                ? undefined
                                : handleCancelEmbeddingChange
                        )();
                    }
                }}
            >
                <Portal>
                    <Dialog.Backdrop />
                    <Dialog.Positioner>
                        <Dialog.Content className="modal-style">
                            <Dialog.Header>بردارسازی دوباره اسناد</Dialog.Header>
                            <Dialog.Body>
                                {isReEmbedding ? (
                                    <VStack gap={4} align="stretch">
                                        <Text>
                                            Re-embedding documents with the new
                                            model…
                                        </Text>
                                        <ReEmbedProgress
                                            progress={reEmbedProgress}
                                        />
                                    </VStack>
                                ) : (
                                    <>
                                        <Text>
                                            Changing the embedding model will
                                            re-embed all existing document
                                            collections with the new model. Your
                                            documents and collections will be
                                            preserved.
                                        </Text>
                                        <Text mt={4} fontWeight="bold">
                                            Are you sure you want to proceed?
                                        </Text>
                                    </>
                                )}
                            </Dialog.Body>
                            {!isReEmbedding && (
                                <Dialog.Footer>
                                    <Button
                                        className="red-button"
                                        mr={3}
                                        onClick={handleCancelEmbeddingChange}
                                    >
                                        Cancel
                                    </Button>
                                    <Button
                                        className="green-button"
                                        onClick={handleConfirmEmbeddingChange}
                                    >
                                        Confirm Change
                                    </Button>
                                </Dialog.Footer>
                            )}
                        </Dialog.Content>
                    </Dialog.Positioner>
                </Portal>
            </Dialog.Root>
        </>
    );
};

export default RagTab;
