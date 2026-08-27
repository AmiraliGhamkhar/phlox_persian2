// Functions to handle and format API errors.
import { toaster } from "@/components/ui/toaster";
import { DEFAULT_TOAST_CONFIG } from "../constants";
import { translatePersian } from "@/i18n/fa";

export class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.status = status;
        this.name = "ApiError";
    }
}

export const handleError = (error) => {
    console.error("Error:", error);

    if (error instanceof ApiError) {
        toaster.create({
            title: `${translatePersian("Error")} ${error.status}`,
            description: translatePersian(error.message),
            type: "error",
            ...DEFAULT_TOAST_CONFIG,
        });
    } else {
        toaster.create({
            title: translatePersian("Error"),
            description: translatePersian("An unexpected error occurred"),
            type: "error",
            ...DEFAULT_TOAST_CONFIG,
        });
    }
};

export const toastApiError = (description, title = "Error") => {
    toaster.create({
        title: translatePersian(title),
        description: translatePersian(description),
        type: "error",
        ...DEFAULT_TOAST_CONFIG,
    });
};

export const toastApiSuccess = (description, title = "Success") => {
    toaster.create({
        title: translatePersian(title),
        description: translatePersian(description),
        type: "success",
        ...DEFAULT_TOAST_CONFIG,
    });
};

