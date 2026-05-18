/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0a0a0a",
          panel: "#111111",
          subtle: "#181818",
          hover: "#1f1f1f",
        },
        border: {
          DEFAULT: "#262626",
          subtle: "#1c1c1c",
        },
        text: {
          DEFAULT: "#e4e4e7",
          muted: "#a1a1aa",
          subtle: "#71717a",
        },
        accent: {
          DEFAULT: "#7c3aed",
          hover: "#8b5cf6",
        },
        sev: {
          critical: "#ef4444",
          high: "#f97316",
          medium: "#eab308",
          low: "#3b82f6",
          info: "#64748b",
          unknown: "#71717a",
        },
        status: {
          queued: "#a1a1aa",
          running: "#3b82f6",
          succeeded: "#10b981",
          failed: "#ef4444",
          cancelled: "#71717a",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "Menlo", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
