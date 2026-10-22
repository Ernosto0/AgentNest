import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Relative base so the built files work from any static host or sub-path.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  // 5173 belongs to the app's frontend; keep both runnable side by side.
  server: { port: 5174 },
})
