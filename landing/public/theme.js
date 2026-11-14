// Runs before first paint: apply the saved theme (or the OS preference) and enable entrance motion.
;(function () {
  var root = document.documentElement
  var theme
  try {
    theme = localStorage.getItem('landing.theme')
  } catch (e) {}
  if (theme !== 'light' && theme !== 'dark') {
    theme = window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  root.dataset.theme = theme
  root.classList.add('js')
})()
