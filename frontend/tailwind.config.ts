import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        lavender: "var(--color-accent)",
        cream: "var(--color-background)",
        warmgray: "var(--color-warm-gray)",
        ink: "var(--color-ink)",
      },
      fontFamily: {
        sans: ["Manrope", "sans-serif"],
        serif: ["PT Serif", "serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;

