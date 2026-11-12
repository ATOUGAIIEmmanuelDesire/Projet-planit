/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ucac: {
          navy: '#0F2C59',
          navyDark: '#0A1E3F',
          orange: '#E85D04',
          orangeHover: '#D05203',
          gold: '#F5A623',
          green: '#10B981',
          bgLight: '#F8FAFC',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [],
}