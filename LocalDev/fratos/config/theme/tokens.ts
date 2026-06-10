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
    danger: T.err,
    warning: T.warn,
  },
  font: {
    sizeXs: 11,
    sizeSm: 12,
    sizeMd: 13,
    sizeLg: 14,
    sizeXl: 16,
    size2xl: 22,
    weightNormal: 400,
    weightMedium: 600,
    weightBold: 700,
    weightBlack: 800,
  },
  space: {
    1: 4,
    2: 8,
    3: 10,
    4: 16,
    5: 20,
    6: 24,
    7: 40,
  },
  radius: {
    sm: 6,
    md: 8,
    lg: 10,
    xl: 12,
  },
} as const;
