/**
 * The icon set.
 *
 * Hand-drawn inline SVG rather than `lucide-react`, for one reason that
 * outweighs the convenience: this frontend has zero runtime dependencies
 * beyond React, and an icon library is 1,500 glyphs shipped so that fourteen
 * can be used. Every path below is on lucide's grid and follows lucide's
 * conventions (24x24 viewBox, 2px stroke, round caps and joins), so swapping to
 * the real package later is a one-line import change per call site.
 *
 * What matters more than the source is that these replaced EMOJI. The previous
 * UI used `🎣 👍 👎 ⚡ ⚑ 📄 ✓ ✗` as iconography. Emoji render as a different
 * picture on every platform, cannot inherit colour or stroke weight, and are
 * announced by screen readers as their CLDR name mid-sentence — "fishing pole
 * Fishack". They were the single biggest thing making a carefully-built system
 * look like a prototype in a screenshot.
 *
 * Accessibility: icons are `aria-hidden` by default because they nearly always
 * sit beside a text label. Pass `title` on the rare standalone one and it
 * becomes a labelled `img` role instead.
 */

import type { SVGProps } from "react";

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "children"> {
  /** Pixel size for both axes. Defaults to 16 — the size next to `text-sm`. */
  size?: number;
  /** Supply only when the icon is the ONLY content of its control. */
  title?: string;
}

/** Shared chrome so an individual icon is nothing but its path data. */
function Svg({ size = 16, title, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      focusable="false"
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

/* ------------------------------------------------------------- navigation -- */

export const ArrowRight = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12h14M12 5l7 7-7 7" />
  </Svg>
);

export const ArrowLeft = (p: IconProps) => (
  <Svg {...p}>
    <path d="M19 12H5M12 19l-7-7 7-7" />
  </Svg>
);

export const ArrowUp = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 19V5M5 12l7-7 7 7" />
  </Svg>
);

export const ChevronRight = (p: IconProps) => (
  <Svg {...p}>
    <path d="m9 18 6-6-6-6" />
  </Svg>
);

export const ChevronDown = (p: IconProps) => (
  <Svg {...p}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
);

export const Menu = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 6h16M4 12h16M4 18h16" />
  </Svg>
);

export const Close = (p: IconProps) => (
  <Svg {...p}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Svg>
);

export const ExternalLink = (p: IconProps) => (
  <Svg {...p}>
    <path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
  </Svg>
);

/* ------------------------------------------------------------------ state -- */

export const Check = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 6 9 17l-5-5" />
  </Svg>
);

/** Escalation and superseded sources. AMBER, never rose — see globals.css. */
export const Flag = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V4s-1 1-4 1-5-2-8-2-4 1-4 1z" />
    <path d="M4 22v-7" />
  </Svg>
);

export const AlertTriangle = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    <path d="M12 9v4M12 17h.01" />
  </Svg>
);

export const Info = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 16v-4M12 8h.01" />
  </Svg>
);

export const ShieldCheck = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 13c0 5-3.5 7.5-7.7 8.9a1 1 0 0 1-.6 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.2-2.7a1 1 0 0 1 1.5 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z" />
    <path d="m9 12 2 2 4-4" />
  </Svg>
);

export const Lock = (p: IconProps) => (
  <Svg {...p}>
    <rect width="18" height="11" x="3" y="11" rx="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </Svg>
);

/* ------------------------------------------------------------- pipeline -- */

export const Search = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </Svg>
);

/** Cache. Replaces the ⚡ emoji. */
export const Bolt = (p: IconProps) => (
  <Svg {...p}>
    <path d="M13 2 3 14h9l-1 8 10-12h-9z" />
  </Svg>
);

export const Gauge = (p: IconProps) => (
  <Svg {...p}>
    <path d="m12 14 4-4" />
    <path d="M3.34 19a10 10 0 1 1 17.32 0" />
  </Svg>
);

export const Clock = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 6v6l4 2" />
  </Svg>
);

export const Layers = (p: IconProps) => (
  <Svg {...p}>
    <path d="m12.8 2.5 8.1 4a1 1 0 0 1 0 1.8l-8.1 4a2 2 0 0 1-1.6 0l-8.1-4a1 1 0 0 1 0-1.8l8.1-4a2 2 0 0 1 1.6 0z" />
    <path d="m22 12.5-9.2 4.6a2 2 0 0 1-1.6 0L2 12.5" />
    <path d="m22 17.5-9.2 4.6a2 2 0 0 1-1.6 0L2 17.5" />
  </Svg>
);

export const Database = (p: IconProps) => (
  <Svg {...p}>
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M3 5v14a9 3 0 0 0 18 0V5" />
    <path d="M3 12a9 3 0 0 0 18 0" />
  </Svg>
);

/* ------------------------------------------------------------- documents -- */

/** The `docs` source type. */
export const FileText = (p: IconProps) => (
  <Svg {...p}>
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z" />
    <path d="M14 2v5h6M9 13h6M9 17h6" />
  </Svg>
);

/** The `changelog` source type — violet, and only ever this. */
export const History = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 3v5h5" />
    <path d="M12 7v5l3 2" />
  </Svg>
);

/** The `ticket` source type. */
export const Ticket = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2z" />
    <path d="M13 5v14" strokeDasharray="2 3" />
  </Svg>
);

export const BookOpen = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 7v14" />
    <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
  </Svg>
);

export const Terminal = (p: IconProps) => (
  <Svg {...p}>
    <path d="m4 17 6-6-6-6M12 19h8" />
  </Svg>
);

export const Copy = (p: IconProps) => (
  <Svg {...p}>
    <rect width="14" height="14" x="8" y="8" rx="2" />
    <path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2" />
  </Svg>
);

/* -------------------------------------------------------------- feedback -- */

export const ThumbsUp = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 10v11H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z" />
    <path d="M7 10l4.4-7.3A2 2 0 0 1 15 4v4h4.6a2 2 0 0 1 2 2.4l-1.4 8A2 2 0 0 1 18.2 20H7" />
  </Svg>
);

export const ThumbsDown = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 14V3H4a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1z" />
    <path d="M7 14l4.4 7.3A2 2 0 0 0 15 20v-4h4.6a2 2 0 0 0 2-2.4l-1.4-8A2 2 0 0 0 18.2 4H7" />
  </Svg>
);

export const Square = (p: IconProps) => (
  <Svg {...p}>
    <rect width="12" height="12" x="6" y="6" rx="1.5" fill="currentColor" stroke="none" />
  </Svg>
);

export const RefreshCw = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
    <path d="M21 3v5h-5" />
    <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
    <path d="M3 21v-5h5" />
  </Svg>
);

export const Building = (p: IconProps) => (
  <Svg {...p}>
    <rect width="16" height="20" x="4" y="2" rx="2" />
    <path d="M9 22v-4h6v4M9 6h.01M15 6h.01M9 10h.01M15 10h.01M9 14h.01M15 14h.01" />
  </Svg>
);

/* ------------------------------------------------------------- wordmark -- */

/**
 * The Fishack mark — a fish mid-leap.
 *
 * Drawn here rather than imported, for the same reason as every icon above:
 * this frontend has no runtime dependencies beyond React, and a logo is four
 * paths.
 *
 * How it is built, because the construction is what makes it maintainable: the
 * fish is authored FACING LEFT on a level axis — body, forked tail, dorsal
 * crest, eye — and the whole group is then rotated into the leap. Tuning the
 * angle is one number, and none of the path data has to be re-derived to do it.
 * Drawing it pre-rotated would bake the angle into twenty coordinates.
 *
 * The crest's base sits INSIDE the body outline rather than on its edge, so the
 * two shapes merge into one silhouette instead of reading as a fin stuck on a
 * fish. That is the difference between the mark working and not working at
 * 16px, where every seam becomes a notch.
 */

/**
 * The fish itself: level, facing left, with the eye knocked out in whatever
 * colour sits behind it.
 *
 * The eye lives INSIDE this fragment rather than being positioned by each
 * caller, so it rotates and scales with the body automatically. Placing it
 * outside meant hand-computing its position for every transform, and it
 * silently drifted off the head the first time the angle changed.
 */
const Fish = ({ eye }: { eye: string }) => (
  <>
    <path
      d="M2.2 16 C4.2 10.6 8.2 7.9 13 7.9 C18.2 7.9 22 11.2 24 16
         C22 20.4 18.2 22.9 13 22.9 C8.2 22.9 4.2 21 2.2 16 Z"
    />
    <path
      d="M22 16 C24.8 13.2 27.4 10.2 29.8 7.4 C29 11 27.6 14 26.2 16
         C27.6 18 29 21 29.8 24.6 C27.4 21.8 24.8 18.8 22 16 Z"
    />
    <path d="M11.4 10.8 C14.4 6.8 18.6 4.9 22.4 6.4 C20 8 19.4 9.6 19.1 11.2 Z" />
    <circle cx="7.8" cy="13.8" r="1.5" fill={eye} />
  </>
);

/**
 * Centre, scale, rotate into the leap, un-centre. Read right to left.
 *
 * `translate(-16 -14)` uses the fish's own bounding-box centre, not the
 * viewBox centre — the tail and the crest push the shape above and right of
 * the middle, and rotating about (16,16) leaves the mark visibly low in its
 * tile. `0.76` is the largest scale at which the tail tip still clears the
 * tile's corner radius.
 */
const leap = (scale: number) =>
  `translate(16 16) scale(${scale}) rotate(-40) translate(-16 -14)`;

/**
 * The mark on its brand tile — the header lockup and the app icon.
 *
 * A filled tile rather than a bare silhouette: at 26px beside the wordmark it
 * holds its own against the text, and it is what a browser tab needs in order
 * to be findable among twenty others.
 */
export function Wordmark({ size = 26, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <rect width="32" height="32" rx="8" className="fill-ocean-600" />
      <g transform={leap(0.76)} fill="#fff">
        <Fish eye="#22738f" />
      </g>
    </svg>
  );
}

/**
 * The silhouette alone, for places that already have a background — an empty
 * state, a loading indicator, a print header.
 */
export function FishMark({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <g transform={leap(0.95)} fill="currentColor">
        <Fish eye="#fff" />
      </g>
    </svg>
  );
}
