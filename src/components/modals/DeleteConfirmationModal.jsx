import { Button, HStack, Heading, Text, Dialog, Portal } from "@chakra-ui/react";

const DeleteConfirmationModal = ({
  isOpen,
  onClose,
  onConfirm,
  itemName,
  title = "حذف",
}) => {
  return (
    <Dialog.Root open={isOpen} size='md' onOpenChange={e => {
      if (!e.open) {
        onClose();
      }
    }}>
      <Portal>

        <Dialog.Backdrop />
        <Dialog.Positioner>
          <Dialog.Content className="modal-style">
            <Dialog.Header>
              <Heading as="h2" size="md" fontFamily="heading">{title}</Heading>
            </Dialog.Header>
            <Dialog.CloseTrigger />
            <Dialog.Body>
              <Text>
                آیا مطمئنید می‌خواهید «{itemName}» را حذف کنید؟ این عملیات قابل
                بازگشت نیست.
              </Text>
            </Dialog.Body>
            <Dialog.Footer>
              <HStack justify="flex-end" width="100%">
                <Button className="red-button" mr={3} onClick={onClose}>
                  انصراف
                </Button>
                <Button className="green-button" onClick={onConfirm}>
                  حذف
                </Button>
              </HStack>
            </Dialog.Footer>
          </Dialog.Content>
        </Dialog.Positioner>

      </Portal>
    </Dialog.Root>
  );
};

export default DeleteConfirmationModal;
