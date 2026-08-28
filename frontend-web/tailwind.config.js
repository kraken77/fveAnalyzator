/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: "#0b1f33",
        antelonGreen: "#2fbf71",
        antelonOrange: "#f28e2b",
        slateMuted: "#566472",
      },
    },
  },
  plugins: [],
}
