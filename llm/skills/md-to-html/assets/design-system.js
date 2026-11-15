const themeToggle = document.querySelector('#theme-toggle');
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const label = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
  themeToggle.setAttribute('aria-label', label);
  themeToggle.setAttribute('aria-pressed', String(theme === 'dark'));
  themeToggle.title = label;
  document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#151c20' : '#f7f5ef';
  try {
    localStorage.setItem('linux-theme', theme);
  } catch {}
  const current = new URL(location.href);
  current.searchParams.set('theme', theme);
  try {
    history.replaceState(null, '', current);
  } catch {}
  // File pages may have separate storage, so lesson links carry the selected theme.
  document.querySelectorAll('a[href]').forEach(link => {
    if (link.getAttribute('href').startsWith('#')) return;
    const url = new URL(link.href);
    if (url.origin === location.origin && url.pathname.endsWith('.html')) {
      url.searchParams.set('theme', theme);
      link.href = url.href;
    }
  });
}
themeToggle.addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
setTheme(document.documentElement.dataset.theme);

if ('IntersectionObserver' in window) {
  const links = [...document.querySelectorAll('nav a')];
  const observer = new IntersectionObserver(entries => {
    const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
    if (!visible.length) return;
    const identifier = visible[0].target.id || visible[0].target.getAttribute('aria-labelledby');
    links.forEach(link => {
      if (link.hash === '#' + identifier) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  }, { rootMargin: '-5% 0px -65% 0px', threshold: 0 });
  document.querySelectorAll('.chapter').forEach(section => observer.observe(section));
}
const menuToggle = document.querySelector('#menu-toggle');
const lessonMenu = document.querySelector('#lesson-menu');
menuToggle.addEventListener('click', () => {
  lessonMenu.hidden = !lessonMenu.hidden;
  document.querySelector('.layout').classList.toggle('menu-hidden', lessonMenu.hidden);
  menuToggle.setAttribute('aria-expanded', String(!lessonMenu.hidden));
  const label = lessonMenu.hidden ? 'Show contents' : 'Hide contents';
  menuToggle.setAttribute('aria-label', label);
  menuToggle.title = label;
});
document.documentElement.classList.add('enhanced');

function reflectDesignTokens() {
  const tokens = getComputedStyle(document.documentElement);
  document.querySelectorAll('[data-token]').forEach(element => {
    element.textContent = tokens.getPropertyValue(element.dataset.token).trim();
  });
}
reflectDesignTokens();
new MutationObserver(reflectDesignTokens).observe(document.documentElement, {
  attributes: true,
  attributeFilter: ['data-theme']
});
