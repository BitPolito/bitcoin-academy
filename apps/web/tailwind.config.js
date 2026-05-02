/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'blue-dark':  '#001CE0',
        'surface':    '#F9F9F9',
        'ink-soft':   '#0a1a4a',
        'rule':       '#E4E6F2',
        'rule-soft':  '#EFF1F8',
        'ok':         '#1a7f3a',
        'warn':       '#a55a00',
        'err':        '#b3261e',
        // legacy — keep until fully migrated
        bitcoin: '#F7931A',
      },
      fontFamily: {
        sans: ['"SF Pro Display"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      maxWidth: {
        '8xl': '1480px',
      },
    },
  },
  plugins: [],
};
