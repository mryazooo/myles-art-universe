document.addEventListener("DOMContentLoaded", () => {
  /* ----- Footer year (if present) ----- */
  const yearSpan = document.querySelector("[data-year]");
  if (yearSpan) {
    yearSpan.textContent = new Date().getFullYear();
  }

  /* ----- Mobile nav toggle ----- */
  const navToggle = document.querySelector(".nav-toggle");
  const mainNav = document.querySelector(".main-nav");

  if (navToggle && mainNav) {
    navToggle.addEventListener("click", () => {
      mainNav.classList.toggle("open");
    });
  }

  /* ----- Lightbox overlay for images ----- */

  // Create lightbox container once and reuse it
  const lightbox = document.createElement("div");
  lightbox.id = "lightbox";
  lightbox.innerHTML = `
    <div class="lightbox-inner">
      <button class="lightbox-close" aria-label="Close image">&times;</button>
      <img src="" alt="">
      <p class="lightbox-caption"></p>
    </div>
  `;
  document.body.appendChild(lightbox);

  const lightboxImg = lightbox.querySelector("img");
  const lightboxCaption = lightbox.querySelector(".lightbox-caption");
  const lightboxClose = lightbox.querySelector(".lightbox-close");

  function openLightbox(img) {
    if (!img) return;
    lightboxImg.src = img.src;
    lightboxImg.alt = img.alt || "";
    lightboxCaption.textContent = img.alt || "";
    lightbox.classList.add("is-open");
    document.body.style.overflow = "hidden"; // prevent background scroll
  }

  function closeLightbox() {
    lightbox.classList.remove("is-open");
    document.body.style.overflow = "";
    lightboxImg.src = "";
    lightboxImg.alt = "";
    lightboxCaption.textContent = "";
  }

  // Close handlers
  lightboxClose.addEventListener("click", closeLightbox);

  // Click outside the inner box closes
  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) {
      closeLightbox();
    }
  });

  // Esc key closes (desktop)
  document.addEventListener("keyup", (event) => {
    if (event.key === "Escape" && lightbox.classList.contains("is-open")) {
      closeLightbox();
    }
  });

  // Images that should trigger the lightbox
  const selectors = [
    ".card-image img",   // Gallery cards
    ".sketch-card img",  // Sketchbook cards
    ".hero-art",         // Hero image on home page
    ".strip-page img"    // "More from Myles" strip tiles
  ];

  const clickableImages = document.querySelectorAll(selectors.join(","));

  clickableImages.forEach((img) => {
    img.style.cursor = "zoom-in";
    img.addEventListener("click", () => openLightbox(img));
  });
});
