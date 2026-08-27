export const formatCollectionName = (name) => name;

export const formatDate = (date) => {
    if (!date) return "";
    return new Date(date).toLocaleDateString("fa-IR", {
        year: "numeric",
        month: "long",
        day: "numeric",
    });
};
