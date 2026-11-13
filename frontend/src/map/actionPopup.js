import { PRIORITY_LABEL, STATUS_LABEL, TYPE_LABEL } from "../actions.js";
import { buildPopup } from "./popups.js";

/** The popup of an action pin, built from plain text (titles are typed by users, so never treated as HTML). */
export function actionPopup(properties) {
  const p = properties || {};
  return buildPopup(p.title || "Action", [
    ["Type", TYPE_LABEL[p.action_type] || p.action_type || "–"],
    ["Priority", PRIORITY_LABEL[p.priority] || p.priority || "–"],
    ["Status", STATUS_LABEL[p.status] || p.status || "–"],
  ]);
}
