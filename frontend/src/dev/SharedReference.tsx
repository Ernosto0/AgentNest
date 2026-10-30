import { useRef, useState } from "react";
import { BottomSheet } from "@/components/BottomSheet";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChoiceField, SelectField, TextAreaField } from "@/components/FormFields";
import { ErrorSummary, Notice, Skeleton, Toast } from "@/components/Feedback";
import { DataTable, FilterBar, ListRow, PageHeader, PanelHeader } from "@/components/Layout";
import { Pagination } from "@/components/Pagination";
import { StatusBadge } from "@/components/StatusBadge";
import { TextField } from "@/components/TextField";
import { STATUS_KEYS } from "@/components/status";
import { AppError } from "@/api/errors";

const COPY = {
  en: {
    heading: "Shared interaction specimens", intro: "Fictional controls; no request is submitted.",
    fields: "Form feedback", name: "Business name", hint: "Entered values stay on screen.", message: "Message", language: "Reply language", optional: "Optional choice", choice: "Keep this draft", invalid: "Review this field", summary: "Review the example errors", action: "Save example", pending: "Saving example", disabled: "Unavailable example", reason: "This example has no connected account.", secondary: "Secondary", ghost: "Quiet action", danger: "Destructive example",
    overlay: "Open example sheet", title: "Review example", description: "Keyboard focus stays inside this sheet. Escape closes the topmost sheet.", nested: "Open nested sheet", previousFocus: "Open with prior focus", child: "Nested example", close: "Close example", note: "Source unavailable", recovery: "Review current sources before deciding.", feedback: "States and feedback", empty: "No example records", emptyDescription: "Create an example when you are ready.", loading: "Loading example records", toast: "Example copied", dismiss: "Dismiss notice", statuses: "Canonical result states", collection: "Rows, filters and pagination", filters: "Example filters", all: "All", filtered: "Needs review", row: "Example record", page: "Page", previous: "Previous", next: "Next", count: "Result", value: "Value", table: "Example values", done: "Finish review",
  },
  tr: {
    previousFocus: "Önceki odakla aç",
    heading: "Ortak etkileşim örnekleri", intro: "Kurgu kontroller; hiçbir istek gönderilmez.",
    fields: "Form geri bildirimi", name: "İşletme adı", hint: "Girilen değerler ekranda kalır.", message: "Mesaj", language: "Yanıt dili", optional: "İsteğe bağlı seçim", choice: "Bu taslağı koru", invalid: "Bu alanı gözden geçirin", summary: "Örnek hataları gözden geçirin", action: "Örneği kaydet", pending: "Örnek kaydediliyor", disabled: "Kullanılamayan örnek", reason: "Bu örneğe bağlı hesap yok.", secondary: "İkincil işlem", ghost: "Sade işlem", danger: "Silme işlemi örneği",
    overlay: "Örnek paneli aç", title: "Örneği gözden geçirin", description: "Klavye odağı bu panelde kalır. Escape en üstteki paneli kapatır.", nested: "İç paneli aç", child: "İç panel örneği", close: "Örneği kapat", note: "Kaynak kullanılamıyor", recovery: "Karar vermeden önce güncel kaynakları gözden geçirin.", feedback: "Durumlar ve geri bildirim", empty: "Örnek kayıt yok", emptyDescription: "Hazır olduğunuzda bir örnek oluşturun.", loading: "Örnek kayıtlar yükleniyor", toast: "Örnek kopyalandı", dismiss: "Bildirimi kapat", statuses: "Kaydın gerçek durumları", collection: "Satırlar, filtreler ve sayfalama", filters: "Örnek filtreler", all: "Tümü", filtered: "İnceleme bekliyor", row: "Örnek kayıt", page: "Sayfa", previous: "Önceki", next: "Sonraki", count: "Sonuç", value: "Değer", table: "Örnek değerler", done: "İncelemeyi bitir",
  },
} as const;

export function SharedReference({ locale }: { locale: "en" | "tr" }) {
  const c = COPY[locale];
  const [open, setOpen] = useState(false);
  const [nested, setNested] = useState(false);
  const [defaultFocus, setDefaultFocus] = useState(false);
  const [name, setName] = useState("");
  const [validation, setValidation] = useState(false);
  const [saved, setSaved] = useState(false);
  const [toast, setToast] = useState(true);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState("all");
  const input = useRef<HTMLInputElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const nestedOpener = useRef<HTMLButtonElement>(null);
  return <section className="grid min-w-0 gap-6" data-testid="shared-reference">
    <PageHeader title={c.heading} description={c.intro} action={<Button ref={opener} data-testid="open-sheet" onClick={() => setOpen(true)}>{c.overlay}</Button>} />
    <Card className="grid gap-5">
      <PanelHeader title={c.fields} />
      {validation && !name.trim() ? <ErrorSummary title={c.summary} errors={[{ id: "reference-name", message: c.invalid }]} /> : null}
      <form className="grid gap-4" noValidate onSubmit={event => { event.preventDefault(); if (!name.trim()) setValidation(true); else setSaved(true); }}>
        <TextField label={c.name} id="reference-name" hint={c.hint} error={validation && !name.trim() ? c.invalid : undefined} value={name} onChange={event => setName(event.target.value)} autoComplete="organization" />
        <TextAreaField label={c.message} hint={c.hint} />
        <SelectField label={c.language}><option value="tr">{locale === "tr" ? "Türkçe" : "Turkish"}</option><option value="en">{locale === "tr" ? "İngilizce" : "English"}</option></SelectField>
        <ChoiceField label={c.choice} hint={c.optional} />
        <div className="flex flex-wrap gap-3"><Button type="submit">{c.action}</Button><Button pending>{c.pending}</Button><Button variant="secondary">{c.secondary}</Button><Button variant="ghost">{c.ghost}</Button><Button variant="danger">{c.danger}</Button></div>
        <Button disabled disabledReason={c.reason}>{c.disabled}</Button>
        {saved ? <Notice title={c.done} live="polite" tone="success" /> : null}
      </form>
    </Card>
    <Card className="grid gap-5"><PanelHeader title={c.feedback} /><Notice title={c.note} tone="attention">{c.recovery}</Notice><ErrorMessage error={new AppError("CONFLICT_STATE", 409, { requestId: "fictional-request" })} /><EmptyState title={c.empty} description={c.emptyDescription} /><Skeleton label={c.loading} />{toast ? <Toast dismissLabel={c.dismiss} onDismiss={() => setToast(false)}>{c.toast}</Toast> : null}</Card>
    <Card className="grid gap-5"><PanelHeader title={c.statuses} /><div className="flex flex-wrap gap-3">{STATUS_KEYS.map(status => <StatusBadge key={status} status={status} simulated={status === "sent"} params={{ time: "19:05" }} />)}</div></Card>
    <Card className="grid gap-5"><PanelHeader title={c.collection} /><FilterBar label={c.filters}><Button variant="secondary" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>{c.all}</Button><Button variant="secondary" aria-pressed={filter === "review"} onClick={() => setFilter("review")}>{c.filtered}</Button></FilterBar><ul><ListRow>{`${c.row} · ${filter === "all" ? c.all : c.filtered} · ${c.page} ${page}`}</ListRow></ul><Pagination label={c.page} previousLabel={c.previous} nextLabel={c.next} onPrevious={page > 1 ? () => setPage(page - 1) : undefined} onNext={page < 3 ? () => setPage(page + 1) : undefined} /><DataTable caption={c.table}><thead><tr><th scope="col" className="p-3">{c.count}</th><th scope="col" className="p-3">{c.value}</th></tr></thead><tbody><tr><td className="p-3">{c.row}</td><td className="p-3">{page}</td></tr></tbody></DataTable></Card>
    {open ? <BottomSheet title={c.title} description={c.description} onClose={() => setOpen(false)} initialFocusRef={input} returnFocusRef={opener} footer={<Button block onClick={() => setOpen(false)}>{c.done}</Button>}><div className="grid gap-5"><TextField label={c.name} ref={input} defaultValue={locale === "tr" ? "Örnek işletme" : "Example business"} /><Button ref={nestedOpener} onClick={() => { setDefaultFocus(false); setNested(true); }}>{c.nested}</Button><Button data-testid="prior-focus-sheet" onClick={() => { input.current?.focus(); setDefaultFocus(true); setNested(true); }}>{c.previousFocus}</Button><div className="grid gap-4">{Array.from({ length: 8 }, (_, index) => <Notice key={index} title={`${c.row} ${index + 1}`}>{c.recovery}</Notice>)}</div></div>{nested ? <BottomSheet title={c.child} returnFocusRef={defaultFocus ? undefined : nestedOpener} onClose={() => setNested(false)}><Button onClick={() => setNested(false)}>{c.close}</Button></BottomSheet> : null}</BottomSheet> : null}
  </section>;
}
