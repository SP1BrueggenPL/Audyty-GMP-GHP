document.addEventListener("DOMContentLoaded", function () {
  var form = document.getElementById("inspection-form");

  // ---- 1) OK/NC/n.d. toggle per punkt checklisty -------------------------
  document.querySelectorAll(".item-row").forEach(function (row) {
    var itemId = row.dataset.itemId;
    var detail = row.querySelector(".nc-detail");
    var radios = row.querySelectorAll('input[name="item_' + itemId + '_result"]');
    function sync() {
      var checked = row.querySelector('input[name="item_' + itemId + '_result"]:checked');
      if (detail) detail.classList.toggle("open", checked && checked.value === "NC");
    }
    radios.forEach(function (r) { r.addEventListener("change", sync); });
    sync();
  });

  if (!form) return;

  // ---- 2) Przedstawiciele obszaru wg wybranej zmiany ---------------------
  var shiftSelect = form.querySelector('select[name="shift"]');
  var repListEl = document.getElementById("area-rep-list");
  var usersUrl = form.dataset.usersUrl;
  var currentReps = []; // [{id, name}]

  function refreshResponsibleSelects() {
    document.querySelectorAll(".responsible-select").forEach(function (select) {
      var previous = select.value;
      select.innerHTML = '<option value="">— wybierz przedstawiciela obszaru —</option>';
      currentReps.forEach(function (rep) {
        var opt = document.createElement("option");
        opt.value = rep.id;
        opt.textContent = rep.name;
        select.appendChild(opt);
      });
      if (currentReps.some(function (r) { return String(r.id) === previous; })) {
        select.value = previous;
      } else if (currentReps.length === 1) {
        select.value = currentReps[0].id;
      }
    });
  }

  function renderRepList(users) {
    if (!repListEl) return;
    if (!users.length) {
      repListEl.innerHTML = '<span class="muted">Brak osób przypisanych do tej zmiany w systemie.</span>';
      currentReps = [];
      refreshResponsibleSelects();
      return;
    }
    repListEl.innerHTML = "";
    users.forEach(function (u) {
      var label = document.createElement("label");
      var checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.name = "area_rep_ids";
      checkbox.value = u.id;
      checkbox.checked = true;
      checkbox.addEventListener("change", function () {
        currentReps = Array.from(repListEl.querySelectorAll('input[type=checkbox]:checked')).map(function (cb) {
          return { id: cb.value, name: cb.nextSibling.textContent };
        });
        refreshResponsibleSelects();
      });
      label.appendChild(checkbox);
      label.appendChild(document.createTextNode(u.name));
      repListEl.appendChild(label);
    });
    currentReps = users.map(function (u) { return { id: String(u.id), name: u.name }; });
    refreshResponsibleSelects();
  }

  function loadRepsForShift(shift) {
    if (!shift || !usersUrl) {
      renderRepList([]);
      return;
    }
    fetch(usersUrl + "?shift=" + encodeURIComponent(shift))
      .then(function (r) { return r.json(); })
      .then(function (data) { renderRepList(data.users || []); })
      .catch(function () { renderRepList([]); });
  }

  if (shiftSelect) {
    shiftSelect.addEventListener("change", function () { loadRepsForShift(shiftSelect.value); });
    if (shiftSelect.value) loadRepsForShift(shiftSelect.value);
  }

  // ---- 3) Dodatkowe niezgodności (formularz "dodaj kolejną") -------------
  var addBtn = document.getElementById("add-extra-nc");
  var container = document.getElementById("extra-nc-container");
  var totalInput = document.getElementById("extra-total-forms");
  var tpl = document.getElementById("extra-nc-template");

  if (addBtn && container && tpl && totalInput) {
    addBtn.addEventListener("click", function () {
      var index = parseInt(totalInput.value, 10);
      var html = tpl.innerHTML.replace(/__prefix__/g, index);
      var wrapper = document.createElement("div");
      wrapper.innerHTML = html;
      container.appendChild(wrapper);
      totalInput.value = index + 1;
      refreshResponsibleSelects();
    });
  }

  // ---- 4) Podpowiedź opisu niezgodności (AI, Azure OpenAI GPT-4o) --------
  var suggestUrl = form.dataset.suggestUrl;
  var csrfToken = form.querySelector('input[name="csrfmiddlewaretoken"]').value;

  document.querySelectorAll(".suggest-ai-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var itemId = btn.dataset.itemId;
      var photoInput = form.querySelector('.photo-input[data-item-id="' + itemId + '"]');
      var statusEl = form.querySelector('.ai-status[data-item-id="' + itemId + '"]');
      var descField = btn.closest(".nc-detail").querySelector(".description-field");

      if (!photoInput || !photoInput.files || !photoInput.files.length) {
        statusEl.textContent = "Najpierw dodaj zdjęcie niezgodności.";
        return;
      }

      var fd = new FormData();
      fd.append("item_id", itemId);
      fd.append("photo", photoInput.files[0]);

      statusEl.textContent = "Analizuję zdjęcie…";
      btn.disabled = true;

      fetch(suggestUrl, { method: "POST", body: fd, headers: { "X-CSRFToken": csrfToken } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          btn.disabled = false;
          if (data.suggestion) {
            descField.value = data.suggestion;
            statusEl.textContent = "Podpowiedź wstawiona - sprawdź i popraw opis przed zapisem.";
          } else if (!data.available) {
            statusEl.textContent = "Funkcja AI nie jest skonfigurowana (brak danych dostępowych Azure OpenAI).";
          } else {
            statusEl.textContent = data.error || "Nie udało się wygenerować podpowiedzi.";
          }
        })
        .catch(function () {
          btn.disabled = false;
          statusEl.textContent = "Błąd połączenia z usługą AI.";
        });
    });
  });
});
