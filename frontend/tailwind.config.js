/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#0d9488",
          dark: "#0f766e",
        },
      },
    },
  },
  plugins: [],
};
