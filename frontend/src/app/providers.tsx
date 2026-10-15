import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import i18n from "@/i18n";
import { LanguageSync } from "./LanguageSync";

export function Providers({ client, children }: { client: QueryClient; children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <LanguageSync />
        {children}
      </QueryClientProvider>
    </I18nextProvider>
  );
}
