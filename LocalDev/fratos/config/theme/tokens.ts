import { T } from "../../lib/theme";

export const tokens = {
  color: {
    bg: T.bg,
    surface: T.sf,
    surfaceHover: T.sfh,
    border: T.bd,
    accent: T.ac,
    accentLight: T.acl,
    text: T.tx,
    textMuted: T.txm,
    success: T.ok,
    error: T.err,
    warning: T.warn,
  },
  space: {
    1: "4px",
    2: "6px",
    3: "10px",
    4: "16px",
    5: "20px",
    6: "24px",
    8: "32px",
  },
  font: {
    sizeSm: "11px",
    sizeMd: "13px",
    sizeLg: "12px",
    sizeXl: "15px",
    size2xl: "22px",
    weightNormal: 400,
    weightSemibold: 600,
    weightBold: 700,
  },
  radius: {
    sm: "6px",
    md: "8px",
    lg: "10px",
    xl: "12px",
  },
} as const;
