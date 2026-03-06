/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./static/**/*.js"],
  theme: {
    extend: {
      colors: {
        "bg-dark": "#0d0e0f",
        "bg-card": "#16181c",
        "bg-elevated": "#1c1e23",
        ink: "#e8eaed",
        "ink-muted": "#9aa0a6",
        "ink-dim": "#5f6368",
        line: "#2d3139",
        accent: "#8ab4f8",
        "accent-hover": "#aecbfa",
        ok: "#81c995",
        error: "#f28b82",
      },
      fontFamily: {
        sans: ["DM Sans", "Segoe UI", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 24px 48px rgba(0, 0, 0, 0.35)",
        "card-hover": "0 8px 24px rgba(0, 0, 0, 0.25)",
        modal: "0 24px 48px rgba(0, 0, 0, 0.5)",
      },
      animation: {
        spin: "spin 0.65s linear infinite",
        reveal: "reveal 0.25s ease",
      },
      keyframes: {
        spin: {
          to: { transform: "rotate(360deg)" },
        },
        reveal: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
