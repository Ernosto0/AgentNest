type Modal = { root: HTMLElement; panel: HTMLElement; previous: HTMLElement | null };
const stack: Modal[] = [];
const backgrounds = new Map<HTMLElement, { inert: string | null; hidden: string | null }>();
let scrollBefore = "";
let observer: MutationObserver | undefined;

function restoreBackground() {
  for (const [element, state] of backgrounds) {
    if (state.inert === null) element.removeAttribute("inert"); else element.setAttribute("inert", state.inert);
    if (state.hidden === null) element.removeAttribute("aria-hidden"); else element.setAttribute("aria-hidden", state.hidden);
  }
  backgrounds.clear();
}

function isolateTopmost() {
  restoreBackground();
  const top = stack.at(-1);
  if (!top) return;
  for (const element of document.body.children) {
    if (!(element instanceof HTMLElement) || element === top.root) continue;
    backgrounds.set(element, { inert: element.getAttribute("inert"), hidden: element.getAttribute("aria-hidden") });
    element.setAttribute("inert", "");
    element.setAttribute("aria-hidden", "true");
  }
}

export function isTopmostModal(root: HTMLElement | null) {
  return stack.at(-1)?.root === root;
}

export function registerModal(root: HTMLElement, panel: HTMLElement, initial?: HTMLElement | null, returnTo?: HTMLElement | null) {
  const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const entry = { root, panel, previous };
  if (stack.length === 0) {
    scrollBefore = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    observer = new MutationObserver(isolateTopmost);
    observer.observe(document.body, { childList: true });
  }
  stack.push(entry);
  // Move focus before hiding the previously focused background from accessibility APIs.
  (initial && panel.contains(initial) ? initial : panel).focus();
  isolateTopmost();
  return () => {
    const wasTopmost = stack.at(-1) === entry;
    const index = stack.indexOf(entry);
    if (index !== -1) stack.splice(index, 1);
    isolateTopmost();
    if (stack.length === 0) {
      observer?.disconnect();
      observer = undefined;
      document.body.style.overflow = scrollBefore;
    }
    if (wasTopmost) {
      const target = returnTo?.isConnected && !returnTo.closest("[inert]") ? returnTo : previous?.isConnected && !previous.closest("[inert]") ? previous : stack.at(-1)?.panel;
      target?.focus();
    }
  };
}

export function tabbableElements(panel: HTMLElement) {
  return [...panel.querySelectorAll<HTMLElement>("a[href], button, input, select, textarea, [tabindex], [contenteditable=true]")].filter(element => {
    if (element.tabIndex < 0 || element.matches(":disabled") || element.closest("[hidden], [inert]")) return false;
    if (element instanceof HTMLInputElement && element.type === "hidden") return false;
    for (let parent: HTMLElement | null = element; parent && parent !== panel; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if (style.display === "none" || style.visibility === "hidden") return false;
    }
    return true;
  });
}
