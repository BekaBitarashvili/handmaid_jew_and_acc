/*
 * Alpine components for the storefront. Loaded (deferred) before Alpine itself,
 * so these are registered on `alpine:init`.
 */
const PHONE = window.matchMedia("(max-width: 47.999rem)");

function lockPageScroll(locked) {
  document.documentElement.classList.toggle("overflow-hidden", locked);
}

document.addEventListener("alpine:init", () => {
  // Shop filters: a full-height sheet on phones, a static column from 768px.
  Alpine.data("filterSheet", () => ({
    open: false,
    lockScroll(open) {
      lockPageScroll(open && PHONE.matches);
    },
  }));
});
