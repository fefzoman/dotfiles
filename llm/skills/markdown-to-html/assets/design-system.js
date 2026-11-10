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
