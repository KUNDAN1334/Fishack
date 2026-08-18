import type { Config } from "tailwindcss";

// Only Tailwind's core utility classes are used anywhere in this app — no
// custom plugins, no arbitrary-value escapes beyond the few noted in
// components. That keeps the build reproducible and the markup readable.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // One accent, used for the brand and for interactive affordances.
        // A support tool should look calm; every additional colour has to
        // earn its place by MEANING something (see globals.css).
        ocean: {
          50: "#eef7fb", 100: "#d5ecf5", 300: "#7fc4de",
          500: "#2b90b6", 600: "#22738f", 700: "#1b5a70", 900: "#123c4b",
        },
      },
    },
  },
  plugins: [],
};
export default config;
