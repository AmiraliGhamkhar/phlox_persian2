import { Button, VStack, HStack, Heading, Input, Textarea, Dialog, Portal } from "@chakra-ui/react";

const LetterTemplateEditModal = ({
  isOpen,
  onClose,
  onSave,
  template,
  setTemplate,
}) => {
  const handleChange = (field, value) => {
    setTemplate((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleSave = () => {
    onSave(template);
  };

  return (
    <Dialog.Root open={isOpen} size='lg' onOpenChange={e => {
      if (!e.open) {
        onClose();
      }
    }}>
      <Portal>

        <Dialog.Backdrop />
        <Dialog.Positioner>
          <Dialog.Content className="modal-style">
            <Dialog.Header>
              <Heading as="h2" size="md" fontFamily="heading">
                {template?.id ? "ویرایش قالب" : "قالب جدید"}
              </Heading>
            </Dialog.Header>
            <Dialog.CloseTrigger />
            <Dialog.Body maxH="40vh" overflowY="auto" className="custom-scrollbar">
              <VStack gap={4}>
                <Input
                  placeholder="نام قالب"
                  value={template?.name || ""}
                  onChange={(e) => handleChange("name", e.target.value)}
                  disabled={template?.name === "Dictation"}
                  className="input-style"
                />
                <Textarea
                  placeholder="دستورهای تولید نامه..."
                  value={template?.instructions || ""}
                  onChange={(e) => handleChange("instructions", e.target.value)}
                  className="input-style"
                />
              </VStack>
            </Dialog.Body>
            <Dialog.Footer>
              <HStack justify="flex-end" width="100%">
                <Button
                  className="red-button"
                  mr={3}
                  onClick={() => {
                    onClose();
                    setTemplate(null);
                  }}
                >
                  انصراف
                </Button>
                <Button className="green-button" onClick={handleSave}>
                  ذخیره
                </Button>
              </HStack>
            </Dialog.Footer>
          </Dialog.Content>
        </Dialog.Positioner>

      </Portal>
    </Dialog.Root>
  );
};

export default LetterTemplateEditModal;
