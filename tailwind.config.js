/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        mint: {
          500: "#A4DED0",
          600: "#92c7ba",
          700: "#78b2a7"
        }
      }
    },
  },
  plugins: [],
}