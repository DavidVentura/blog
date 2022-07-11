/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./blog/**/*.html"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "Noto Sans", "sans-serif", "Segoe UI Symbol"]
      },
      fontSize: {
        base: ['1rem', '1.4']
      }
    },
  },
  plugins: [],
}
