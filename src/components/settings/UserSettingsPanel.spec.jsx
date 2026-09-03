import { describe, it, expect, vi, afterEach } from "vitest";
import { screen, cleanup, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "../../test/utils";
import UserSettingsPanel from "./UserSettingsPanel";

// The template managers hit the API on mount; their internals are out of
// scope for this inventory. ChatSettingsPanel is pure (no API) and is
// rendered for real so the quick-chat pairs are pinned too.
vi.mock("./TemplateSettingsPanel", () => ({
    default: () => <div data-testid="note-templates-panel-body" />,
}));
vi.mock("./LetterTemplatesPanel", () => ({
    default: () => <div data-testid="letter-templates-panel-body" />,
}));

/**
 * Control inventory for UserSettingsPanel — the T1-5 baseline.
 *
 * The plan assumed the user panel was a flat field list; as built it is a
 * tabbed layout (General / note templates / letter templates / quick chat /
 * advanced) that already provides the intended progressive disclosure
 * (identity + template defaults visible by default; rarely-edited content
 * behind tabs). This inventory pins that structure so it is protected.
 */
describe("UserSettingsPanel — control inventory", () => {
    afterEach(cleanup);

    const userSettings = {
        name: "Dr. Test",
        specialty: "Cardiology",
        quick_chat_1_title: "ت1",
        quick_chat_2_title: "ت2",
        quick_chat_3_title: "ت3",
        quick_chat_1_prompt: "پ1",
        quick_chat_2_prompt: "پ2",
        quick_chat_3_prompt: "پ3",
        default_template: "soap_default",
        default_letter_template_id: 7,
        advanced_options: { require_scribe_consent: true },
    };

    const renderPanel = (setUserSettings = vi.fn()) =>
        renderWithProviders(
            <UserSettingsPanel
                isCollapsed={false}
                setIsCollapsed={() => {}}
                userSettings={userSettings}
                setUserSettings={setUserSettings}
                specialties={["Cardiology", "Neurology"]}
                templates={[
                    { template_key: "soap_default", template_name: "SOAP" },
                ]}
                letterTemplates={[{ id: 7, name: "مرخصی درمانی" }]}
                setTemplates={() => {}}
            />,
        );

    it("offers the five tabs; the general tab is selected by default", () => {
        renderPanel();

        const tabs = screen.getAllByRole("tab");
        expect(tabs.map((t) => t.dataset.testid)).toEqual([
            "user-tab-general",
            "user-tab-note-templates",
            "user-tab-letter-templates",
            "user-tab-quick-chat",
            "user-tab-advanced",
        ]);
        const selected = tabs.filter(
            (t) => t.getAttribute("aria-selected") === "true",
        );
        expect(selected).toHaveLength(1);
        expect(selected[0].dataset.testid).toBe("user-tab-general");
    });

    it("the general tab shows identity + both template defaults, bound", () => {
        renderPanel();

        expect(screen.getByTestId("user-name-input")).toHaveValue("Dr. Test");
        expect(screen.getByTestId("user-specialty-select")).toHaveValue(
            "Cardiology",
        );
        expect(screen.getByTestId("user-default-template-select")).toHaveValue(
            "soap_default",
        );
        expect(screen.getByTestId("user-default-letter-template-select")).toHaveValue(
            "7",
        );
        for (const id of [
            "user-name-input",
            "user-specialty-select",
            "user-default-template-select",
            "user-default-letter-template-select",
        ]) {
            expect(screen.getByTestId(id)).toBeVisible();
        }
    });

    it("the quick-chat tab exposes the three quick-chat title inputs, bound", () => {
        // Tab contents stay mounted (inactive ones are hidden), so the pair
        // inputs can be inventoried directly by their stable class.
        renderPanel();

        const titleInputs = document.querySelectorAll(".quick-chat-title-input");
        expect([...titleInputs].map((el) => el.value)).toEqual([
            "ت1",
            "ت2",
            "ت3",
        ]);
    });

    it("the advanced tab shows the two expert switches, bound to state", () => {
        renderPanel();

        // Explicitly set to true in userSettings
        expect(
            screen.getByTestId("user-advanced-option-require_scribe_consent"),
        ).toHaveAttribute("data-state", "checked");
        // Not set → falls back to the schema default (false)
        expect(
            screen.getByTestId("user-advanced-option-store_original_pdfs"),
        ).toHaveAttribute("data-state", "unchecked");
    });

    // Note: the switch write path (onCheckedChange -> setUserSettings) is not
    // asserted here. Chakra v3's Switch is Ark-UI based and its checked-change
    // event relies on pointer/activation behavior that jsdom does not simulate,
    // so it cannot be driven from a DOM test. The switch's state *binding*
    // (checked/unchecked reflecting advanced_options and schema defaults) is
    // asserted above, which is the property the T1-5 inventory must protect.

    it("name input changes flow through setUserSettings", () => {
        let nextValue = null;
        const setUserSettings = vi.fn((updater) => {
            if (typeof updater === "function") nextValue = updater(userSettings);
        });
        renderPanel(setUserSettings);

        fireEvent.change(screen.getByTestId("user-name-input"), {
            target: { value: "Dr. New" },
        });

        expect(setUserSettings).toHaveBeenCalled();
        expect(nextValue.name).toBe("Dr. New");
    });
});
