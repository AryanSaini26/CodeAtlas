/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "#050505",
        layer: "#131313",
        surface: {
          DEFAULT: "#201f1f",
          lo: "#1c1b1b",
          hi: "#2a2a2a",
          top: "#353534",
        },
        panel: "#131313",
        border: "rgba(255,255,255,0.06)",
        cyan: {
          DEFAULT: "#00f0ff",
          dim: "#00dbe9",
        },
        violet: {
          DEFAULT: "#bd00ff",
        },
        amber: {
          DEFAULT: "#f59e0b",
        },
        good: "#22c55e",
        bad: "#ef4444",
        accent: "#00f0ff",
        text: {
          1: "#e4e4e7",
          2: "#a1a1aa",
          3: "#71717a",
          4: "#52525b",
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        head: ['"Space Grotesk"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      backdropBlur: {
        glass: '18px',
      },
      animation: {
        'fade-up': 'fadeUp 0.25s ease forwards',
        'slide-right': 'slideRight 0.22s ease forwards',
        'pulse-dot': 'pulseDot 2s ease infinite',
      },
      keyframes: {
        fadeUp: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        slideRight: {
          from: { opacity: '0', transform: 'translateX(20px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        pulseDot: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.5', transform: 'scale(0.8)' },
        },
      },
    },
  },
  plugins: [],
};
