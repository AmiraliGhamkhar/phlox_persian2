import { Button, Dialog, Portal } from "@chakra-ui/react";

const DeleteConfirmationModal = ({
    isOpen,
    onClose,
    onDelete,
    patientName,
}) => {
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
                        <Dialog.Header>حذف بیمار</Dialog.Header>
                        <Dialog.CloseTrigger />
                        <Dialog.Body>
                            {patientName
                                ? `Are you sure you want to delete ${patientName}?`
                                : "آیا مطمئنید می‌خواهید این بیمار را حذف کنید؟"}
                        </Dialog.Body>
                        <Dialog.Footer>
                            <Button className="red-button" mr={3} onClick={onDelete}>
                                حذف
                            </Button>
                            <Button className="green-button" onClick={onClose}>
                                انصراف
                            </Button>
                        </Dialog.Footer>
                    </Dialog.Content>
                </Dialog.Positioner>

            </Portal>
        </Dialog.Root>
    );
};

export default DeleteConfirmationModal;
