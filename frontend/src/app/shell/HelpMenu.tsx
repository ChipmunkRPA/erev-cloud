// Help menu (DESIGN_SYSTEM DS-CMP-01 item 8; SCREENS §0.4 SF-27 placement, OQ-S-10). A ghost icon button
// with the Question icon. An item renders only when what it opens is built (BUILD_SPEC XR-14): WEB-9
// builds "About eRev Cloud"; the keyboard shortcuts dialog, the guided tour (DMO) and the user guide add
// their items when they are built.
import { useSearchParams } from "react-router";

import { Question } from "../../components/icons/registry";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { t } from "../../lib/i18n/t";
import { ABOUT_DIALOG, DIALOG_PARAM } from "./AboutDialog";

export function HelpMenu() {
  const [, setParams] = useSearchParams();
  const items: MenuItem[] = [
    {
      id: "about",
      label: t("shell.help.about"),
      onSelect: () => {
        setParams((current) => {
          const next = new URLSearchParams(current);
          next.set(DIALOG_PARAM, ABOUT_DIALOG);
          return next;
        });
      },
    },
  ];
  return (
    <Menu
      label={t("shell.help.label")}
      icon={Question}
      iconOnly
      variant="ghost"
      align="end"
      items={items}
    />
  );
}
