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

  // ---- 2) Przedstawiciele obszaru (Użytkownicy obszaru) wg działu/zmiany -
  // Widget "dostępni / wybrani": kliknięcie w dostępnego dodaje go do wybranych,
  // ✕ przy wybranym usuwa go z powrotem do dostępnych.
  var shiftSelect = form.querySelector('select[name="shift"]');
  var areaDetailSelect = form.querySelector('select[name="area_detail"]');
  var repListEl = document.getElementById("area-rep-list");
  var usersUrl = form.dataset.usersUrl;
  var areaCode = form.dataset.areaCode;
  var allCandidates = []; // [{id, name}] - wszyscy kandydaci dla obecnego działu/zmiany
  var selectedIds = new Set();
  // W edycji istniejącej inspekcji wstępnie zaznaczamy tylko już zapisanych
  // przedstawicieli (nie wszystkich kandydatów) - tylko przy pierwszym wczytaniu.
  var initialSelectedIds = form.dataset.preselectedReps
    ? form.dataset.preselectedReps.split(",").filter(Boolean)
    : null;
  var currentReps = []; // [{id, name}] - aktualnie wybrani (do wypełniania selectów "odpowiedzialny")

  function refreshResponsibleSelects() {
    document.querySelectorAll(".responsible-select").forEach(function (select) {
      // select.value na pusty string przy pierwszym renderze - w edycji istniejącej
      // niezgodności wracamy wtedy do zapisanej wcześniej osoby (data-selected).
      var previous = select.value || select.dataset.selected || "";
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

  function renderDualList() {
    if (!repListEl) return;
    if (!allCandidates.length) {
      repListEl.innerHTML = '<span class="muted">Brak osób do wyboru dla tego działu. Sprawdź w Użytkownicy, czy potrzebne osoby mają ' +
        'jednocześnie: rolę „Użytkownik obszaru” ORAZ ustawiony Dział zgodny z tym obszarem (samo zaznaczenie roli nie wystarczy).</span>';
      currentReps = [];
      refreshResponsibleSelects();
      return;
    }

    var available = allCandidates.filter(function (u) { return !selectedIds.has(String(u.id)); });
    var selected = allCandidates.filter(function (u) { return selectedIds.has(String(u.id)); });

    repListEl.innerHTML =
      '<div class="dual-list">' +
      '<div class="dual-list-col"><div class="dual-list-title">Dostępni</div><div class="dual-list-items" data-role="available"></div></div>' +
      '<div class="dual-list-col"><div class="dual-list-title">Wybrani</div><div class="dual-list-items" data-role="selected"></div></div>' +
      "</div>";
    var availableEl = repListEl.querySelector('[data-role="available"]');
    var selectedEl = repListEl.querySelector('[data-role="selected"]');

    if (!available.length) {
      availableEl.innerHTML = '<span class="muted">— brak —</span>';
    }
    available.forEach(function (u) {
      var item = document.createElement("div");
      item.className = "dual-list-item";
      item.textContent = u.name;
      item.addEventListener("click", function () {
        selectedIds.add(String(u.id));
        renderDualList();
      });
      availableEl.appendChild(item);
    });

    if (!selected.length) {
      selectedEl.innerHTML = '<span class="muted">— brak —</span>';
    }
    selected.forEach(function (u) {
      var item = document.createElement("div");
      item.className = "dual-list-item is-selected";
      var nameSpan = document.createElement("span");
      nameSpan.textContent = u.name;
      var removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "dual-list-remove";
      removeBtn.textContent = "✕";
      removeBtn.addEventListener("click", function () {
        selectedIds.delete(String(u.id));
        renderDualList();
      });
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "area_rep_ids";
      hidden.value = u.id;
      item.appendChild(nameSpan);
      item.appendChild(removeBtn);
      item.appendChild(hidden);
      selectedEl.appendChild(item);
    });

    currentReps = selected.map(function (u) { return { id: String(u.id), name: u.name }; });
    refreshResponsibleSelects();
  }

  function loadRepsForArea() {
    if (!usersUrl) {
      allCandidates = [];
      selectedIds = new Set();
      renderDualList();
      return;
    }
    var params = new URLSearchParams();
    if (areaCode) params.set("area_code", areaCode);
    if (areaDetailSelect && areaDetailSelect.value) params.set("area_detail", areaDetailSelect.value);
    if (shiftSelect && shiftSelect.value) params.set("shift", shiftSelect.value);

    fetch(usersUrl + "?" + params.toString())
      .then(function (r) { return r.json(); })
      .then(function (data) {
        allCandidates = data.users || [];
        if (initialSelectedIds) {
          selectedIds = new Set(initialSelectedIds);
          initialSelectedIds = null;
        } else {
          selectedIds = new Set(allCandidates.map(function (u) { return String(u.id); })); // domyślnie wszyscy zaznaczeni
        }
        renderDualList();
      })
      .catch(function () {
        allCandidates = [];
        selectedIds = new Set();
        renderDualList();
      });
  }

  if (shiftSelect) shiftSelect.addEventListener("change", loadRepsForArea);
  if (areaDetailSelect) areaDetailSelect.addEventListener("change", loadRepsForArea);
  loadRepsForArea();

  // ---- 3) Dodatkowe niezgodności (formularz "dodaj kolejną", niezwiązane
  //         z konkretnym punktem lub podpięte pod dowolny wybrany punkt) ----
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
      container.appendChild(wrapper.firstElementChild);
      totalInput.value = index + 1;
      refreshResponsibleSelects();
    });
  }

  // ---- 3b) "+" Dodaj kolejną niezgodność bezpośrednio przy punkcie -------
  var itemExtraTpl = document.getElementById("item-extra-nc-template");

  function wireRemoveItemNc(block) {
    var btn = block.querySelector(".remove-item-nc");
    if (!btn) return;
    btn.addEventListener("click", function () {
      if (block.dataset.hasAdvanced === "1") {
        if (!confirm("Ta niezgodność ma już wykonane działania naprawcze (przyczyna/działania korygujące). Na pewno ją usunąć?")) {
          return;
        }
      }
      block.remove();
    });
  }

  document.querySelectorAll(".item-nc-list").forEach(function (listEl) {
    listEl.querySelectorAll(".item-nc-block").forEach(wireRemoveItemNc);
  });

  document.querySelectorAll(".add-item-nc").forEach(function (addItemBtn) {
    addItemBtn.addEventListener("click", function () {
      var itemId = addItemBtn.dataset.itemId;
      var listEl = form.querySelector('.item-nc-list[data-item-id="' + itemId + '"]');
      var itemTotalInput = form.querySelector('input[name="item_' + itemId + '_extra-TOTAL_FORMS"]');
      if (!itemExtraTpl || !listEl || !itemTotalInput) return;
      var index = parseInt(itemTotalInput.value, 10);
      var html = itemExtraTpl.innerHTML.replace(/__ITEMID__/g, itemId).replace(/__prefix__/g, index);
      var wrapper = document.createElement("div");
      wrapper.innerHTML = html;
      var block = wrapper.firstElementChild;
      listEl.appendChild(block);
      wireRemoveItemNc(block);
      itemTotalInput.value = index + 1;
      refreshResponsibleSelects();
    });
  });

  // Gdy wynik punktu zmienia się z NC na OK/n.d., a punkt ma już zaawansowaną
  // (wypełnioną przez osobę odpowiedzialną) niezgodność - dopytaj przed zmianą,
  // żeby nie skasować przypadkiem wykonanej pracy przy zapisie formularza.
  document.querySelectorAll(".item-row[data-has-advanced-nc]").forEach(function (row) {
    var itemId = row.dataset.itemId;
    var radios = row.querySelectorAll('input[name="item_' + itemId + '_result"]');
    radios.forEach(function (radio) {
      radio.addEventListener("change", function () {
        if (radio.value !== "NC") {
          if (!confirm("Ten punkt ma już wykonane działania naprawcze dla zapisanej niezgodności. Zmiana wyniku na \"" +
              (radio.value === "OK" ? "OK" : "n/d") + "\" usunie tę niezgodność wraz z działaniami przy zapisie. Kontynuować?")) {
            var ncRadio = row.querySelector('input[name="item_' + itemId + '_result"][value="NC"]');
            if (ncRadio) ncRadio.checked = true;
            row.querySelector(".nc-detail").classList.add("open");
          }
        }
      });
    });
  });

  // ---- 4) Podpowiedź opisu niezgodności (AI, Azure OpenAI GPT-4o) --------
  // Delegacja zdarzeń na formularzu - obejmuje też bloki dodane dynamicznie
  // (dodatkowe niezgodności per punkt / niezwiązane z punktem).
  var suggestUrl = form.dataset.suggestUrl;
  var csrfToken = form.querySelector('input[name="csrfmiddlewaretoken"]').value;

  form.addEventListener("click", function (e) {
    var btn = e.target.closest(".suggest-ai-btn");
    if (!btn) return;

    var block = btn.closest(".item-nc-block") || btn.closest(".extra-nc-block") || btn.closest(".nc-detail");
    var photoInput = block.querySelector(".photo-input");
    var statusEl = block.querySelector(".ai-status");
    var descField = block.querySelector(".description-field");
    // item-nc-list nosi data-item-id dla WSZYSTKICH bloków danego punktu (główny +
    // dodatkowe przez "+"), więc to najpewniejsze źródło - data-item-id na przycisku
    // dotyczy tylko bloku głównego.
    var listEl = btn.closest(".item-nc-list");
    var itemId = (listEl && listEl.dataset.itemId) || btn.dataset.itemId || (photoInput && photoInput.dataset.itemId) || "";

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
        } else if (!data.mismatch_point) {
          statusEl.textContent = data.error || "Nie udało się wygenerować podpowiedzi.";
        }
        if (data.mismatch_point) {
          alert(
            "To zdjęcie wygląda na niepasujące do bieżącego punktu.\n\n" +
            "Sugerowany punkt: " + data.mismatch_point +
            (data.mismatch_reason ? "\nUzasadnienie: " + data.mismatch_reason : "") +
            "\n\nSprawdź i w razie potrzeby przenieś tę niezgodność pod właściwy punkt."
          );
        }
      })
      .catch(function () {
        btn.disabled = false;
        statusEl.textContent = "Błąd połączenia z usługą AI.";
      });
  });
});
