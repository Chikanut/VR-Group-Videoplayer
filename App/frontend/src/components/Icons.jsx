import React from 'react';

// Stroke icons in the style of the approved design (24px grid, currentColor).
const PATHS = {
  logo: <><path d="M3 8a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-4l-3-3-3 3H5a2 2 0 0 1-2-2z" /><circle cx="8" cy="11" r="1.5" /><circle cx="16" cy="11" r="1.5" /></>,
  play: <path d="M7 5v14l12-7z" fill="currentColor" stroke="none" />,
  resume: <path d="M7 5v14l12-7z" />,
  pause: <><rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none" /><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none" /></>,
  stop: <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none" />,
  recenter: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></>,
  sleep: <path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z" />,
  wake: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  sync: <><path d="M21 12a9 9 0 0 1-15.5 6.2M3 12a9 9 0 0 1 15.5-6.2" /><path d="M21 4v5h-5M3 20v-5h5" /></>,
  download: <><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" /></>,
  sound: <><path d="M11 5 6 9H2v6h4l5 4z" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /></>,
  qr: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3" /></>,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  power: <><path d="M12 3v9" /><path d="M6.3 7.3a8 8 0 1 0 11.4 0" /></>,
};

export default function Icon({ name, size = 16 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name]}
    </svg>
  );
}
