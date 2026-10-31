# AgentNest design preview

A standalone, interactive visual concept for a redesigned AgentNest Today screen. It uses fictional studio and customer data. All actions are browser-local; nothing connects to the AgentNest API or Instagram. Refresh resets the preview.

## Open locally

From this directory, run a static HTTP server against `dist`, for example:

```powershell
..\..\backend\.venv\Scripts\python.exe -m http.server 5180 --bind 127.0.0.1 --directory dist
```

Then open http://127.0.0.1:5180. The files can also be opened directly from `dist/index.html`.

## Explore

- Review, edit, approve or reject the three sample decisions.
- Create a draft; it appears in the Content preview.
- Open Inbox, Content, Approvals, Assistant, Knowledge and Insights from the sidebar.
- Switch between English and Turkish.
- Search with the search button or Ctrl/Cmd+K.
- Resize to a phone viewport to see the bottom navigation and compact layout.

## Visual direction

Warm off-white canvas, charcoal-green navigation, deep teal actions, pale sage surfaces, Manrope headings and Inter UI text. The overview, decisions, assistant activity and upcoming content each have a distinct visual treatment.

Google Fonts are loaded over HTTPS with system-font fallbacks. Studio imagery is from Unsplash (bundled locally; source URLs in `assets-sources.txt`).
