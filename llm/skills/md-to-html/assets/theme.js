let initialTheme = new URLSearchParams(location.search).get('theme');
if (initialTheme !== 'light' && initialTheme !== 'dark') {
  try {
    initialTheme = localStorage.getItem('linux-theme');
  } catch {}
}
document.documentElement.dataset.theme = initialTheme === 'dark' ? 'dark' : 'light';
