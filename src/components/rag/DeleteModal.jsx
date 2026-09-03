// Modal component to confirm delete operations for collections or files.
import { Button, Spinner, Text, Dialog, Portal } from "@chakra-ui/react";

const DeleteModal = ({ isOpen, onClose, onDelete, item }) => {
    const isDeleting = isOpen && !item;
    if (!item) return null; // Don't render if no item to delete

    return (
        <Dialog.Root open={isOpen} onOpenChange={e => {
            if (!e.open) {
                onClose();
            }
        }}>
            <Portal>

                <Dialog.Backdrop />
                <Dialog.Positioner>
                    <Dialog.Content className="modal-style">
                        <Dialog.Header>
                            {item.type === "file" ? "حذف فایل" : "حذف مجموعه"}
                        </Dialog.Header>
                        <Dialog.CloseTrigger />
                        <Dialog.Body>
                            {isDeleting ? (
                                <Spinner size="md" />
                            ) : (
                                <Text>
                                    {item.type === "file"
                                        ? `آیا از حذف فایل «${item.name}» از مجموعه «${item.collection}» مطمئن هستید؟ این عمل قابل بازگشت نیست.`
                                        : `آیا از حذف مجموعه «${item.name}» و همه فایل‌های آن مطمئن هستید؟ این عمل قابل بازگشت نیست.`}
                                </Text>
                            )}
                        </Dialog.Body>
                        <Dialog.Footer>
                            <Button
                                className="red-button"
                                mr={3}
                                onClick={onDelete}
                                disabled={isDeleting}
                            >
                                {isDeleting ? "در حال حذف..." : "حذف"}
                            </Button>
                            <Button
                                className="green-button"
                                onClick={onClose}
                                disabled={isDeleting}
                            >
                                لغو
                            </Button>
                        </Dialog.Footer>
                    </Dialog.Content>
                </Dialog.Positioner>

            </Portal>
        </Dialog.Root>
    );
};

export default DeleteModal;
