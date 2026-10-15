import type { EditorProps } from "./fields";
import { HoursEditor } from "./HoursEditor";
import { MoneyEditor } from "./MoneyEditor";
import {
  AddressEditor,
  BooleanEditor,
  EmailEditor,
  EnumEditor,
  LocalizedTextEditor,
  PhoneEditor,
  StringListEditor,
  TextEditor,
  UrlEditor,
} from "./SimpleEditors";

/** The editor for one value type. Remount it (via `key`) when the type changes. */
export function ValueEditor({ valueType, ...props }: EditorProps & { valueType: string }) {
  switch (valueType) {
    case "money":
      return <MoneyEditor {...props} />;
    case "weekly_hours":
      return <HoursEditor {...props} />;
    case "text":
      return <TextEditor {...props} />;
    case "localized_text":
      return <LocalizedTextEditor {...props} />;
    case "phone":
      return <PhoneEditor {...props} />;
    case "email":
      return <EmailEditor {...props} />;
    case "address":
      return <AddressEditor {...props} />;
    case "url":
      return <UrlEditor {...props} />;
    case "boolean":
      return <BooleanEditor {...props} />;
    case "enum":
      return <EnumEditor {...props} />;
    case "string_list":
      return <StringListEditor {...props} />;
    default:
      return null;
  }
}
