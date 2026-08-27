// Keep production builds network-independent. The previous next/font/google
// imports downloaded Vazirmatn and Geist during every build, which made Docker
// builds fail whenever Google Fonts was unavailable. The CSS theme already has
// Persian-friendly system fallbacks, so no runtime class is required here.
export const fontVariables = '';
