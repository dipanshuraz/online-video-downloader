/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./static/**/*.js"],
  theme: {
    extend: {
      colors: {
        "bg-dark": "#050511",
        "bg-card": "rgba(18, 18, 28, 0.65)",
        "bg-elevated": "rgba(30, 30, 46, 0.7)",
        "ink": "#f8f9fa",
        "ink-muted": "#a1a1aa",
        "ink-dim": "#71717a",
        "line": "rgba(255, 255, 255, 0.08)",
        "line-light": "rgba(255, 255, 255, 0.15)",
        "accent": "#a855f7",
        "accent-hover": "#c084fc",
        "accent-glow": "rgba(168, 85, 247, 0.35)",
        "ok": "#10b981",
        "error": "#ef4444",
      },
      fontFamily: {
        sans: ["Outfit", "DM Sans", "Segoe UI", "system-ui", "sans-serif"],
      },
      boxShadow: {
        "card": "0 8px 32px 0 rgba(0, 0, 0, 0.3)",
        "card-hover": "0 12px 48px 0 rgba(168, 85, 247, 0.15)",
        "modal": "0 24px 64px rgba(0, 0, 0, 0.6)",
        "glow": "0 0 20px rgba(168, 85, 247, 0.4)",
      },
      backdropBlur: {
        "glass": "16px",
      },
      animation: {
        "spin-slow": "spin 3s linear infinite",
        "reveal": "reveal 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "blob": "blob 7s infinite",
        "pulse-glow": "pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
      keyframes: {
        spin: {
          to: { transform: "rotate(360deg)" },
        },
        reveal: {
          "0%": { opacity: "0", transform: "translateY(12px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        blob: {
          "0%": { transform: "translate(0px, 0px) scale(1)" },
          "33%": { transform: "translate(30px, -50px) scale(1.1)" },
          "66%": { transform: "translate(-20px, 20px) scale(0.9)" },
          "100%": { transform: "translate(0px, 0px) scale(1)" },
        },
        "pulse-glow": {
          "0%, 100%": { opacity: 1, boxShadow: "0 0 15px rgba(168, 85, 247, 0.4)" },
          "50%": { opacity: .8, boxShadow: "0 0 25px rgba(168, 85, 247, 0.7)" },
        }
      },
    },
  },
  plugins: [],
};
