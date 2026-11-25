/*
 * Alpine components for the storefront. Loaded (deferred) before Alpine itself,
 * so these are registered on `alpine:init`.
 */
const PHONE = window.matchMedia("(max-width: 47.999rem)");
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)");
const MOUSE = window.matchMedia("(hover: hover) and (pointer: fine)");

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

  // Product gallery: one scroll-snap track for phone swipe and desktop thumbnails,
  // plus a fullscreen <dialog> viewer.
  Alpine.data("gallery", (count) => ({
    count,
    index: 0,
    zoomIndex: 0,
    zoomed: false,

    init() {
      window.addEventListener("gallery:show", (event) => this.go(event.detail));
    },
    clamp(i) {
      return Math.max(0, Math.min(this.count - 1, i));
    },
    scrollTrack(track, i, smooth = true) {
      track.scrollTo({
        left: i * track.clientWidth,
        behavior: smooth && !REDUCED_MOTION.matches ? "smooth" : "auto",
      });
    },
    sync() {
      const track = this.$refs.track;
      this.index = this.clamp(Math.round(track.scrollLeft / track.clientWidth));
    },
    go(i) {
      this.index = this.clamp(i);
      this.scrollTrack(this.$refs.track, this.index);
    },

    openZoom(i) {
      this.zoomIndex = this.clamp(i);
      this.$refs.dialog.showModal();
      lockPageScroll(true);
      this.$nextTick(() => this.scrollTrack(this.$refs.zoomTrack, this.zoomIndex, false));
    },
    closeZoom() {
      this.$refs.dialog.close();
    },
    onClose() {
      lockPageScroll(false);
      this.zoomed = false;
      this.go(this.zoomIndex); // land on the photo that was last viewed
    },
    zoomSync() {
      const track = this.$refs.zoomTrack;
      const i = this.clamp(Math.round(track.scrollLeft / track.clientWidth));
      if (i !== this.zoomIndex) this.zoomed = false;
      this.zoomIndex = i;
    },
    zoomGo(i) {
      this.zoomed = false;
      this.zoomIndex = this.clamp(i);
      this.scrollTrack(this.$refs.zoomTrack, this.zoomIndex);
    },
    // Mouse: click to magnify 2x around the pointer. Touch screens pinch-zoom natively.
    toggleZoom(event) {
      if (!MOUSE.matches) return;
      this.zoomed = !this.zoomed;
      this.moveZoom(event);
    },
    moveZoom(event) {
      if (!this.zoomed) return;
      const img = event.currentTarget;
      const box = img.getBoundingClientRect();
      const x = ((event.clientX - box.left) / box.width) * 100;
      const y = ((event.clientY - box.top) / box.height) * 100;
      img.style.transformOrigin = `${x}% ${y}%`;
    },
  }));

  // Variant pills: price, availability and photo follow the choice, without a request.
  Alpine.data("variantPicker", (dataId) => ({
    variants: [],
    selected: null,

    init() {
      const source = document.getElementById(dataId);
      this.variants = source ? JSON.parse(source.textContent) : [];
      const first = this.variants.find((v) => v.available) || this.variants[0];
      this.selected = first ? first.id : null;
    },
    get current() {
      return this.variants.length > 1 ? this.variants.find((v) => v.id === this.selected) : null;
    },
    choose(id) {
      const variant = this.variants.find((v) => v.id === id);
      if (variant && variant.image !== null) {
        window.dispatchEvent(new CustomEvent("gallery:show", { detail: variant.image }));
      }
    },
  }));
});
