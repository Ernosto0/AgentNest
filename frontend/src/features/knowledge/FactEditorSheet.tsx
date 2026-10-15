import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Fact, FactCategory, TemplateItem } from "@/api/types";
import { Button } from "@/components/Button";
import { BottomSheet } from "@/components/BottomSheet";
import { ErrorMessage } from "@/components/ErrorMessage";
import { TextField } from "@/components/TextField";
import { AppError } from "@/api/errors";
import { VALUE_TYPES } from "./editors/valueTypes";
import { SelectField } from "./editors/fields";
import type { FactValue } from "./editors/fields";
import { ValueEditor } from "./editors/ValueEditor";
import { isCandidate, useCreateFact, useFactTransition, useUpdateFact } from "./hooks";
import { keyPrefix, pickLabel, slugFromLabel } from "./labels";

export type EditorTarget =
  | { mode: "create"; category: FactCategory; item: TemplateItem | null }
  | { mode: "edit"; fact: Fact; item: TemplateItem | null };

interface Props {
  workspaceId: string;
  currency: string;
  canVerify: boolean;
  target: EditorTarget;
  onClose: () => void;
}

const WINDOW_CATEGORIES: FactCategory[] = ["promotion", "custom"];

/** Create or edit one fact. Staff edits are sent to the owner as a suggestion (HTTP 202). */
export function FactEditorSheet({ workspaceId, currency, canVerify, target, onClose }: Props) {
  const { t, i18n } = useTranslation();
  const create = useCreateFact(workspaceId);
  const update = useUpdateFact(workspaceId);
  const transition = useFactTransition(workspaceId);

  const editing = target.mode === "edit" ? target.fact : null;
  const item = target.item;
  const category: FactCategory = target.mode === "edit" ? target.fact.category : target.category;
  const isNamed = editing === null && (item === null || item.pattern !== null); // needs a label
  const valueTypes = editing
    ? [editing.value_type]
    : item
      ? item.value_types
      : [...VALUE_TYPES];

  const [valueType, setValueType] = useState(valueTypes[0] ?? "text");
  const [value, setValue] = useState<FactValue | null>(editing ? editing.value : null);
  const [labelTr, setLabelTr] = useState("");
  const [labelEn, setLabelEn] = useState("");
  const [criticality, setCriticality] = useState<"critical" | "standard">("standard");
  const [validFrom, setValidFrom] = useState(editing?.valid_from ?? "");
  const [validUntil, setValidUntil] = useState(editing?.valid_until ?? "");
  const [reason, setReason] = useState("");
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [sentAsSuggestion, setSentAsSuggestion] = useState(false);

  const showWindow =
    canVerify && (WINDOW_CATEGORIES.includes(category) || Boolean(editing?.valid_from || editing?.valid_until));
  const pending = create.isPending || update.isPending || transition.isPending;
  const error = create.error ?? update.error ?? transition.error;

  const title = editing
    ? pickLabel(editing.label, i18n.language)
    : item?.key
      ? pickLabel(item.label, i18n.language)
      : t("knowledge.editor.addNamed", { kind: t(`knowledge.category.${category}`) });

  const labelName = (labelTr || labelEn).trim();
  const canSave = value !== null && !pending && (!isNamed || labelName !== "");

  const finish = (result: Parameters<typeof isCandidate>[0]) => {
    if (isCandidate(result)) setSentAsSuggestion(true);
    else onClose();
  };

  const save = () => {
    if (value === null) return;
    const note = reason.trim() || null;
    if (editing) {
      update.mutate(
        {
          factId: editing.id,
          body: {
            expected_version: editing.current_version,
            value,
            reason: note,
            ...(showWindow && (validFrom || null) !== editing.valid_from
              ? { valid_from: validFrom || null }
              : {}),
            ...(showWindow && (validUntil || null) !== editing.valid_until
              ? { valid_until: validUntil || null }
              : {}),
          },
        },
        { onSuccess: finish },
      );
      return;
    }
    const key = item?.key ?? `${keyPrefix(item, category)}.${slugFromLabel(labelName)}`;
    create.mutate(
      {
        key,
        value,
        value_type: valueType,
        reason: note,
        ...(isNamed
          ? { label: { ...(labelTr.trim() ? { tr: labelTr.trim() } : {}), ...(labelEn.trim() ? { en: labelEn.trim() } : {}) } }
          : {}),
        ...(item === null ? { criticality } : {}),
        ...(showWindow && validFrom ? { valid_from: validFrom } : {}),
        ...(showWindow && validUntil ? { valid_until: validUntil } : {}),
      },
      { onSuccess: finish },
    );
  };

  const archive = () => {
    if (!editing) return;
    transition.mutate(
      { factId: editing.id, action: "archive", expectedVersion: editing.current_version },
      { onSuccess: onClose },
    );
  };

  const description = item ? pickLabel(item.description, i18n.language) : null;

  return (
    <BottomSheet
      title={title}
      onClose={onClose}
      footer={
        sentAsSuggestion ? (
          <Button block onClick={onClose}>
            {t("common.close")}
          </Button>
        ) : (
          <div className="flex flex-col gap-2">
            <Button block disabled={!canSave} onClick={save}>
              {pending ? t("knowledge.actions.saving") : canVerify ? t("knowledge.actions.save") : t("knowledge.actions.suggest")}
            </Button>
            {editing && canVerify ? (
              confirmArchive ? (
                <div className="flex gap-2">
                  <Button variant="danger" className="flex-1" disabled={pending} onClick={archive}>
                    {t("knowledge.actions.confirmArchive")}
                  </Button>
                  <Button variant="secondary" className="flex-1" onClick={() => setConfirmArchive(false)}>
                    {t("knowledge.actions.cancel")}
                  </Button>
                </div>
              ) : (
                <Button variant="ghost" block onClick={() => setConfirmArchive(true)}>
                  {t("knowledge.actions.archive")}
                </Button>
              )
            ) : null}
          </div>
        )
      }
    >
      {sentAsSuggestion ? (
        <p role="status" className="rounded-lg bg-amber-50 p-3 text-base text-amber-900 ring-1 ring-amber-400">
          {t("knowledge.editor.sentAsSuggestion")}
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          {description ? <p className="text-sm text-slate-600">{description}</p> : null}
          {!canVerify ? (
            <p className="rounded-lg bg-slate-100 p-3 text-sm text-slate-800">{t("knowledge.editor.staffNote")}</p>
          ) : null}

          {isNamed ? (
            <div className="flex flex-col gap-3">
              <TextField
                label={t("knowledge.editor.labelTr")}
                value={labelTr}
                maxLength={100}
                onChange={(event) => setLabelTr(event.target.value)}
              />
              <TextField
                label={t("knowledge.editor.labelEn")}
                value={labelEn}
                maxLength={100}
                onChange={(event) => setLabelEn(event.target.value)}
              />
            </div>
          ) : null}

          {valueTypes.length > 1 && editing === null ? (
            <SelectField
              label={t("knowledge.editor.valueType")}
              value={valueType}
              onChange={(event) => {
                setValueType(event.target.value);
                setValue(null);
              }}
            >
              {valueTypes.map((type) => (
                <option key={type} value={type}>
                  {t(`knowledge.valueType.${type}`)}
                </option>
              ))}
            </SelectField>
          ) : null}

          {item === null && editing === null ? (
            <SelectField
              label={t("knowledge.editor.criticality")}
              value={criticality}
              onChange={(event) => setCriticality(event.target.value === "critical" ? "critical" : "standard")}
            >
              <option value="standard">{t("knowledge.criticality.standard")}</option>
              <option value="critical">{t("knowledge.criticality.critical")}</option>
            </SelectField>
          ) : null}

          <ValueEditor
            key={valueType}
            valueType={valueType}
            value={value}
            onChange={setValue}
            currency={currency}
            allowedValues={item?.allowed_values ?? []}
          />

          {showWindow ? (
            <fieldset className="flex flex-col gap-3 rounded-xl p-3 ring-1 ring-slate-200">
              <legend className="px-1 text-sm font-medium">{t("knowledge.editor.validity")}</legend>
              <TextField
                label={t("knowledge.editor.validFrom")}
                type="date"
                value={validFrom}
                onChange={(event) => setValidFrom(event.target.value)}
              />
              <TextField
                label={t("knowledge.editor.validUntil")}
                type="date"
                value={validUntil}
                onChange={(event) => setValidUntil(event.target.value)}
              />
            </fieldset>
          ) : null}

          <TextField
            label={t("knowledge.editor.reason")}
            value={reason}
            maxLength={500}
            onChange={(event) => setReason(event.target.value)}
          />

          {error ? <ErrorMessage error={error} /> : null}
          {error instanceof AppError && error.fieldErrors.length > 0 ? (
            <ul className="list-disc pl-5 text-sm text-red-800">
              {error.fieldErrors.map((fieldError) => (
                <li key={`${fieldError.field}-${fieldError.code}`}>
                  {t(`knowledge.fieldErrors.${fieldError.code}`, {
                    defaultValue: t("knowledge.fieldErrors.invalid"),
                  })}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </BottomSheet>
  );
}
