document.addEventListener("DOMContentLoaded", function () {
  var links = Array.prototype.slice.call(document.querySelectorAll(".lightbox-link"));
  if (!links.length) return;

  var overlay = document.createElement("div");
  overlay.className = "lightbox-overlay";
  overlay.innerHTML =
    '<button type="button" class="lightbox-close" aria-label="Zamknij">✕</button>' +
    '<button type="button" class="lightbox-prev" aria-label="Poprzednie">‹</button>' +
    '<img class="lightbox-img" alt="">' +
    '<button type="button" class="lightbox-next" aria-label="Następne">›</button>' +
    '<div class="lightbox-footer">' +
    '<span class="lightbox-caption"></span>' +
    '<a class="lightbox-download btn btn-outline btn-sm" download>⬇ Pobierz</a>' +
    "</div>";
  document.body.appendChild(overlay);

  var imgEl = overlay.querySelector(".lightbox-img");
  var captionEl = overlay.querySelector(".lightbox-caption");
  var downloadEl = overlay.querySelector(".lightbox-download");
  var prevBtn = overlay.querySelector(".lightbox-prev");
  var nextBtn = overlay.querySelector(".lightbox-next");

  var currentGroup = [];
  var currentIndex = 0;

  function showAt(index) {
    if (!currentGroup.length) return;
    currentIndex = (index + currentGroup.length) % currentGroup.length;
    var link = currentGroup[currentIndex];
    imgEl.src = link.getAttribute("href");
    downloadEl.href = link.getAttribute("href");
    captionEl.textContent = link.dataset.caption || "";
    var multi = currentGroup.length > 1;
    prevBtn.style.display = multi ? "" : "none";
    nextBtn.style.display = multi ? "" : "none";
  }

  function open(link) {
    var group = link.dataset.lightbox || "";
    currentGroup = links.filter(function (l) { return (l.dataset.lightbox || "") === group; });
    showAt(currentGroup.indexOf(link));
    overlay.classList.add("open");
    document.body.style.overflow = "hidden";
  }

  function close() {
    overlay.classList.remove("open");
    document.body.style.overflow = "";
  }

  links.forEach(function (link) {
    link.addEventListener("click", function (e) {
      e.preventDefault();
      open(link);
    });
  });

  overlay.querySelector(".lightbox-close").addEventListener("click", close);
  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) close();
  });
  prevBtn.addEventListener("click", function () { showAt(currentIndex - 1); });
  nextBtn.addEventListener("click", function () { showAt(currentIndex + 1); });

  document.addEventListener("keydown", function (e) {
    if (!overlay.classList.contains("open")) return;
    if (e.key === "Escape") close();
    if (e.key === "ArrowLeft") showAt(currentIndex - 1);
    if (e.key === "ArrowRight") showAt(currentIndex + 1);
  });
});
