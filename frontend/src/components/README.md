# Shared UI migration

Session03 migrates shared controls to the Session02 semantic utilities. Existing
imports and props continue to work. Feature APIs, authorization, query ownership,
state transitions and localized error catalogs remain unchanged.

## Forms and actions

```tsx
<TextField
  id="workspace-name"
  ref={nameRef}
  label={t("wizard.name")}
  hint={hint}
  error={errors.name}
  value={name}
  onChange={event => setName(event.target.value)}
/>
<Button type="submit" pending={save.isPending} disabledReason={unavailableReason}>
  {save.isPending ? pendingLabel : saveLabel}
</Button>
```

`TextField`, `TextAreaField`, `SelectField` and `ChoiceField` preserve native
controls and caller IDs, values, autocomplete, names and descriptions. Hints and
inline errors are linked through `aria-describedby`; errors set `aria-invalid`.
Use stable explicit IDs when linking `ErrorSummary` entries. Summary links move
focus to fields without discarding input. Feature validators decide when errors
exist; shared controls do not infer server or business rules. Keep passwords and
customer text out of browser persistence.

`FormFields.tsx` exports textarea/select/checkbox-radio helpers. The old
`features/knowledge/editors/fields.tsx` path re-exports textarea/select for current
consumers. New auth/onboarding consumers should import the shared path. Readonly,
required and disabled remain native attributes. Phone form text is16px.

`Button` keeps `type="button"` as its default. `pending` disables duplicate
activation, adds `aria-busy` and a decorative spinner, and preserves its visible
label; pass localized pending text as children when needed. `disabledReason` is
visible text associated with the button, never only a hover tooltip. Adding or
removing it preserves the existing button node/focus. Pass a localized accessible
name for icon-only buttons. Pending does not mean an external effect succeeded.

## Sheets and drawers

```tsx
const trigger = useRef<HTMLButtonElement>(null);
const firstField = useRef<HTMLInputElement>(null);

<Button ref={trigger} onClick={() => setOpen(true)}>{openLabel}</Button>
{open && <BottomSheet title={title} description={description}
  onClose={requestClose} initialFocusRef={firstField} returnFocusRef={trigger}
  dismissible={!saving} footer={actions}>
  <TextField ref={firstField} label={fieldLabel} />
</BottomSheet>}
```

The sheet is the shared modal/drawer primitive. It traps Tab/Shift+Tab, isolates
background content with `inert` and `aria-hidden`, contains scrolling, supports
phone safe areas, and restores the original attributes and scroll style on close.
Only the topmost nested sheet handles Escape/backdrop. Focus defaults to the
panel; choose a deliberate initial field or safe action with `initialFocusRef`.
For pointer-opened dialogs, supply `returnFocusRef`: Safari/WebKit does not
necessarily focus a clicked button. Without it, focus returns to the previously
focused element. Detached explicit openers fall back to prior focus or the parent
modal. Do not pass newly created ref objects on every render.

`onClose` receives every allowed dismissal (button, Escape or backdrop), so the
feature can confirm substantive dirty edits. `dismissible={false}` disables those
routes during a genuinely noncancellable action. It does not cancel a request.
Long editor redesign and dirty-form ownership remain in their feature sessions;
avoid introducing new nested forms merely because nesting is technically safe.

## Layout and feedback

- `PageHeader` and `PanelHeader`: title, description, optional context/action.
  Session04 can use them for shell/page context; Session05 for entry/onboarding.
- `FilterBar`: labelled native links/buttons; callers own URL state and use
  `aria-current`/`aria-pressed`. It does not invent tab keyboard semantics.
- `ListRow` and `DataTable`: divided rows and a labelled locally scrollable table.
  Keep native table headers and captions. Features still own selection/data scope.
- `Pagination`: optional previous/next callbacks and localized labels. The caller
  owns cursors and pending state. The reference uses a real bounded1–3 fixture;
  later list migrations can adopt it without a new pagination/data contract.
- `Notice`: static by default. Use `live="polite"` only for new async information;
  `assertive` is reserved for blocking failures. Conflict/removed-source notices
  use explicit localized title/body and the authoritative error/state.
- `Toast`: dismissible noncritical status. No timer; the caller controls lifetime.
  Never use a toast as sole evidence of a critical operation's success.
- `Skeleton`: one polite loading label and decorative shapes, separate from empty
  and failure. `EmptyState`, `ErrorMessage` and `FullScreenStatus` remain distinct.
- `StatusBadge` keeps the existing centralized state-to-label/icon mapping and
  per-result `SimulatedBadge`; color never replaces a label or changes semantics.

All new primitives are exercised in `dev/SharedReference.tsx`, a DEV-only local
fixture without API calls. See `dev/README.md` for entry and browser reproduction.
Feature-wide adoption stays with its owning session; do not replace status names
or permission rules during a presentation migration.
