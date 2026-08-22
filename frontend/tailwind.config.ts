import type { Config } from "tailwindcss";

/**
 * The design token layer.
 *
 * Everything visual in Fishack resolves to a value in this file. Nothing here
 * is decoration: this is a tool someone uses while deciding whether to TRUST a
 * machine-generated answer, so the palette is one accent plus grey, and every
 * other colour is reserved for a specific meaning (see `app/globals.css`).
 *
 * Three rules the rest of the app depends on:
 *
 *   1. ONE accent — `ocean`. Brand, links, interactive affordances, cited
 *      markers. A second brand colour would mean the accent no longer signals
 *      "you can act on this".
 *   2. Semantic colour is a CLOSED SET — amber, rose, emerald, violet — and
 *      each has exactly one job. A colour outside that set, or inside it with
 *      the wrong job, is a bug.
 *   3. Numbers are DATA, not prose. Scores, latencies, costs, token counts and
 *      identifiers use the `mono` stack with `tabular-nums`. This is why the
 *      eye can find the number on a dense page without any colour at all.
 *
 * PRODUCTION NOTE: a design system this small does not need a token pipeline
 * (Style Dictionary, Figma Tokens). Past two products sharing a brand it does,
 * and this file becomes generated output rather than a source of truth.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /**
         * The brand accent. Extended from the original five stops to a full
         * scale so that hover, ring, subtle-fill and text-on-fill states each
         * have a stop that meets contrast rather than being faked with opacity.
         *
         * `ocean-600` on white is 5.1:1 — AA for body text. `ocean-500` is
         * 3.4:1, which is AA for large text and for non-text UI (borders,
         * icons) and is used only there.
         */
        ocean: {
          50: "#f0f8fb",
          100: "#d9edf6",
          200: "#b4dcec",
          300: "#7fc4de",
          400: "#49a8cb",
          500: "#2b90b6",
          600: "#22738f",
          700: "#1b5a70",
          800: "#174a5c",
          900: "#123c4b",
          950: "#0a2531",
        },
        /**
         * The page's structural greys. Named rather than reaching for
         * `slate-200` inline, so "what colour is a hairline" has one answer.
         */
        line: {
          DEFAULT: "#e3e8ee", // hairline separators — the app's primary structure
          strong: "#cdd5df", // input borders, anything that must read as an edge
        },
        surface: {
          DEFAULT: "#ffffff", // cards, panels, anything raised off the page
          sunken: "#f7f9fb", // table headers, code blocks, inset wells
          page: "#fbfcfd", // the page itself — barely off-white, not grey
        },
      },

      fontFamily: {
        // System stacks, deliberately. A webfont is a network dependency and a
        // layout-shift risk on a page whose job is to be read; the repo also
        // builds offline, which a next/font/google call would break.
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Inter",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        // Used for everything that is DATA rather than prose. See rule 3 above.
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "JetBrains Mono",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },

      /**
       * A deliberate type scale, replacing the `text-[11px]` / `text-[13px]`
       * escapes that were scattered through the previous UI. Nine steps, and
       * nothing between them.
       *
       * Body is 15px rather than Tailwind's 16 because the docs column is
       * measured to ~72ch: at 16px that line runs long enough to lose the
       * reader's place on a 15" laptop, which is the machine this gets read on.
       */
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.01em" }],
        xs: ["0.75rem", { lineHeight: "1.125rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.65" }],
        lg: ["1.0625rem", { lineHeight: "1.6" }],
        xl: ["1.25rem", { lineHeight: "1.4", letterSpacing: "-0.01em" }],
        "2xl": ["1.5rem", { lineHeight: "1.3", letterSpacing: "-0.015em" }],
        "3xl": ["1.875rem", { lineHeight: "1.2", letterSpacing: "-0.02em" }],
        "4xl": ["2.375rem", { lineHeight: "1.12", letterSpacing: "-0.025em" }],
        "5xl": ["3rem", { lineHeight: "1.05", letterSpacing: "-0.03em" }],
      },

      borderRadius: {
        // Four steps. Anything that needs a fifth is probably the wrong shape.
        sm: "0.25rem", // inline chips, citation markers
        md: "0.375rem", // buttons, inputs
        lg: "0.5rem", // cards, source rows
        xl: "0.75rem", // panels, dialogs
        "2xl": "1rem", // message bubbles
      },

      boxShadow: {
        // Structure comes from hairlines, not shadows. These exist only for
        // things that genuinely float above the page.
        pop: "0 1px 2px rgba(16,24,40,0.04), 0 8px 24px -6px rgba(16,24,40,0.12)",
        card: "0 1px 2px rgba(16,24,40,0.04)",
      },

      maxWidth: {
        prose: "44rem", // ~72ch at 15px — the docs reading column
        shell: "90rem", // the outer page frame
      },

      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "sheet-in": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 160ms ease-out both",
        "sheet-in": "sheet-in 180ms cubic-bezier(0.32, 0.72, 0, 1) both",
      },
    },
  },
  plugins: [],
};

export default config;
