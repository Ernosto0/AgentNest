import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/Button";
import { ValueEditor } from "./editors/ValueEditor";
import type { FactValue } from "./editors/fields";
import type { NormalizedValue } from "./hooks";

/**
 * An owner answer that carries a price, hours or a contact is not saved as free text. The owner
 * enters it in the typed editor, and that value (not the sentence) becomes the verified fact.
 */
export function OwnerAnswerSave({
  editor,
  currency,
  busy,
  onSave,
}: {
  editor: string;
  currency: string;
  busy: boolean;
  onSave: (value: NormalizedValue) => void;
}) {
  const { t } = useTranslation();
  const [value, setValue] = useState<FactValue | null>(null);
  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-action/25 bg-assistant/40 p-3">
      <p className="text-metadata text-primary">
        {t("knowledge.suggestions.needsEditor", { kind: t(`knowledge.suggestions.editorKind.${editor}`) })}
      </p>
      <ValueEditor
        key={editor}
        valueType={editor}
        value={null}
        onChange={setValue}
        currency={currency}
        allowedValues={[]}
      />
      <div>
        <Button disabled={busy || value === null} onClick={() => value && onSave({ value_type: editor, value })}>
          {t("knowledge.suggestions.saveTyped")}
        </Button>
      </div>
    </div>
  );
}
