import type { FactCategory } from "@/api/types";
import { BookIcon } from "@/components/icons";
import { CATEGORY_ICON } from "./presentation";

/** The category's icon on a soft tile; `attention` marks a category that blocks setup. */
export function CategoryGlyph({
  category,
  tone = "neutral",
  size = "md",
}: {
  category: FactCategory;
  tone?: "neutral" | "attention" | "selected";
  size?: "sm" | "md";
}) {
  const Icon = CATEGORY_ICON[category] ?? BookIcon;
  const toneClass = {
    neutral: "bg-surface-subtle text-action",
    attention: "bg-attention-subtle text-attention",
    selected: "bg-action text-on-action",
  }[tone];
  const sizeClass = size === "sm" ? "size-7 rounded-md text-[0.9375rem]" : "size-9 rounded-lg text-base";
  return (
    <span aria-hidden="true" className={`flex shrink-0 items-center justify-center transition-colors ${sizeClass} ${toneClass}`}>
      <Icon />
    </span>
  );
}
