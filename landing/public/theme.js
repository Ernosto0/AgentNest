// Runs before first paint: apply the visitor's saved theme (light unless they chose dark) and enable entrance motion.
;(function () {
  var root = document.documentElement
  var theme
  try {
    theme = localStorage.getItem('landing.theme')
  } catch (e) {}
  if (theme !== 'light' && theme !== 'dark') theme = 'light'
  root.dataset.theme = theme
  root.classList.add('js')
})()
