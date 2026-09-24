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

  var MAX_PHOTOS = 10;

  // ---- 1a) Akumulator zdjęć (max 10) - "multiple" na inpucie typu file ---
  // NIE działa dobrze z capture="environment" na tabletach/telefonach: każde
  // wywołanie aparatu NADPISUJE poprzednią selekcję zamiast ją uzupełniać.
  // Ten kod gromadzi pliki z kolejnych wywołań w osobnej tablicy i za każdym
  // razem odtwarza input.files (przez DataTransfer) tak, żeby zwykły submit
  // formularza (i cała logika po stronie serwera) działały bez zmian.
  function enhancePhotoInput(input) {
    if (input.dataset.photoEnhanced === "1") return;
    input.dataset.photoEnhanced = "1";
    var files = [];

    var wrap = document.createElement("div");
    wrap.className = "photo-upload-wrap";
    input.insertAdjacentElement("afterend", wrap);

    var thumbsEl = document.createElement("div");
    thumbsEl.className = "photo-thumbs";
    var countEl = document.createElement("div");
    countEl.className = "muted photo-count";
    wrap.appendChild(thumbsEl);
    wrap.appendChild(countEl);

    function rebuildInputFiles() {
      var dt = new DataTransfer();
      files.forEach(function (f) { dt.items.add(f); });
      input.files = dt.files;
    }

    function render() {
      thumbsEl.innerHTML = "";
      files.forEach(function (f, idx) {
        var item = document.createElement("div");
        item.className = "photo-thumb";
        var img = document.createElement("img");
        img.src = URL.createObjectURL(f);
        var rm = document.createElement("button");
        rm.type = "button";
        rm.className = "photo-thumb-remove";
        rm.textContent = "✕";
        rm.addEventListener("click", function () {
          files.splice(idx, 1);
          rebuildInputFiles();
          render();
        });
        item.appendChild(img);
        item.appendChild(rm);
        thumbsEl.appendChild(item);
      });
      countEl.textContent = files.length + " / " + MAX_PHOTOS + " zdjęć";
    }

    input.addEventListener("change", function () {
      var incoming = Array.prototype.slice.call(input.files || []);
      var room = MAX_PHOTOS - files.length;
      if (incoming.length > room && room >= 0) {
        alert("Można dodać maksymalnie " + MAX_PHOTOS + " zdjęć do jednej niezgodności.");
      }
      incoming.slice(0, Math.max(room, 0)).forEach(function (f) { files.push(f); });
      rebuildInputFiles();
      render();
    });

    render();
  }

  // ---- 1b) Dyktowanie opisu niezgodności (Web Speech API) ----------------
  // Brak wsparcia w przeglądarce (np. Firefox) - po prostu nie dodajemy
  // przycisku, reszta formularza działa normalnie.
  var SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;

  function enhanceMic(descField) {
    if (descField.dataset.micEnhanced === "1" || !SpeechRecognitionCtor) return;
    descField.dataset.micEnhanced = "1";

    var micBtn = document.createElement("button");
    micBtn.type = "button";
    micBtn.className = "btn btn-outline btn-sm mic-btn";
    micBtn.textContent = "🎤 Dyktuj opis";
    descField.insertAdjacentElement("afterend", micBtn);

    var recognition = new SpeechRecognitionCtor();
    recognition.lang = "pl-PL";
    recognition.interimResults = false;
    recognition.continuous = true;
    var listening = false;

    function stopUi() {
      listening = false;
      micBtn.textContent = "🎤 Dyktuj opis";
      micBtn.classList.remove("mic-active");
    }

    recognition.addEventListener("result", function (e) {
      var transcript = "";
      for (var i = e.resultIndex; i < e.results.length; i++) {
        transcript += e.results[i][0].transcript;
      }
      transcript = transcript.trim();
      if (transcript) {
        descField.value = (descField.value ? descField.value.replace(/\s+$/, "") + " " : "") + transcript;
      }
    });
    recognition.addEventListener("end", stopUi);
    recognition.addEventListener("error", stopUi);

    micBtn.addEventListener("click", function () {
      if (listening) {
        recognition.stop();
        return;
      }
      try {
        recognition.start();
        listening = true;
        micBtn.textContent = "⏹ Zatrzymaj dyktowanie";
        micBtn.classList.add("mic-active");
      } catch (err) {
        stopUi();
      }
    });
  }

  function enhanceBlock(block) {
    var photoInput = block.querySelector(".photo-input");
    var descField = block.querySelector(".description-field");
    if (photoInput) enhancePhotoInput(photoInput);
    if (descField) enhanceMic(descField);
  }

  document.querySelectorAll(".photo-input").forEach(enhancePhotoInput);
  document.querySelectorAll(".description-field").forEach(enhanceMic);

  // ---- 1c) Sprawdzone pomieszczenia/miejsca (WED) - checkboxy zamiast -----
  // wolnego tekstu, zsynchronizowane z ukrytym polem tekstowym (bez zmian
  // po stronie zapisu - nadal wysyła się zwykłe pole rooms_checked).
  (function () {
    var roomsTextarea = form.querySelector(".rooms-checked-textarea");
    var roomsCheckboxes = form.querySelectorAll(".room-checked-checkbox");
    if (!roomsTextarea || !roomsCheckboxes.length) return;

    roomsTextarea.style.display = "none";
    var existingLines = roomsTextarea.value.split("\n").map(function (l) { return l.trim(); }).filter(Boolean);

    function syncTextarea() {
      var selected = Array.prototype.filter.call(roomsCheckboxes, function (c) { return c.checked; })
        .map(function (c) { return c.value; });
      roomsTextarea.value = selected.join("\n");
    }

    roomsCheckboxes.forEach(function (cb) {
      if (existingLines.indexOf(cb.value) !== -1) cb.checked = true;
      cb.addEventListener("change", syncTextarea);
    });
    syncTextarea();
  })();

  // ---- 2) Przedstawiciele obszaru (Użytkownicy obszaru) wg działu/zmiany -
  // Widget "dostępni / wybrani": kliknięcie w dostępnego dodaje go do wybranych,
  // ✕ przy wybranym usuwa go z powrotem do dostępnych. Pola "Osoba odpowiedzialna"
  // przy każdej niezgodności pokazują CAŁĄ pulę kandydatów (allCandidates), nie
  // tylko tych oznaczonych jako "obecni" na liście przedstawicieli - to dwie
  // niezależne decyzje audytora.
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

  function refreshResponsibleSelects() {
    document.querySelectorAll(".responsible-select").forEach(function (select) {
      // select.value na pusty string przy pierwszym renderze - w edycji istniejącej
      // niezgodności wracamy wtedy do zapisanej wcześniej osoby (data-selected).
      var previous = select.value || select.dataset.selected || "";
      select.innerHTML = '<option value="">— wybierz osobę odpowiedzialną —</option>';
      allCandidates.forEach(function (rep) {
        var opt = document.createElement("option");
        opt.value = rep.id;
        opt.textContent = rep.name;
        select.appendChild(opt);
      });
      if (allCandidates.some(function (r) { return String(r.id) === previous; })) {
        select.value = previous;
      }
    });
  }

  function renderDualList() {
    if (!repListEl) return;
    if (!allCandidates.length) {
      repListEl.innerHTML = '<span class="muted">Brak osób do wyboru dla tego działu/zmiany. Kandydatem może być osoba z rolą ' +
        'działową (Pakownia/Produkcja, Techniczny, Logistyka) pasującą do tego obszaru, osoba z rolą „Użytkownik obszaru” i ' +
        'dopasowanym polem Dział, albo dowolna osoba przypisana do tej zmiany (Użytkownicy → edycja konta).</span>';
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

  // ---- 3) Dodawanie/usuwanie niezgodności + podpowiedź AI - WSZYSTKO przez
  // delegację zdarzeń na formularzu (jeden nasłuchiwacz na całość zamiast
  // osobnych na każdym przycisku). To naprawia przycisk "+ Dodaj kolejną
  // niezgodność do tego punktu", który na niektórych tabletach nie reagował
  // na dotyk mimo widocznego podświetlenia - z wieloma osobnymi
  // nasłuchiwaczami na stronie z dużą liczbą punktów, jeden wyjątek w pętli
  // dowiązującej mógł przerwać dowiązywanie kolejnych przycisków; delegacja
  // jest odporna na to strukturalnie, bo sprawdza cel kliknięcia dopiero
  // w momencie kliknięcia, nie przy starcie strony.
  var addExtraBtn = document.getElementById("add-extra-nc");
  var extraContainer = document.getElementById("extra-nc-container");
  var extraTotalInput = document.getElementById("extra-total-forms");
  var extraTpl = document.getElementById("extra-nc-template");
  var itemExtraTpl = document.getElementById("item-extra-nc-template");
  var suggestUrl = form.dataset.suggestUrl;
  var csrfTokenInput = form.querySelector('input[name="csrfmiddlewaretoken"]');

  function removeNcBlock(block) {
    if (block.dataset.hasAdvanced === "1") {
      if (!confirm("Ta niezgodność ma już wykonane działania naprawcze (przyczyna/działania korygujące). Na pewno ją usunąć?")) {
        return;
      }
    }
    block.remove();
  }

  function handleAiSuggest(btn) {
    var block = btn.closest(".item-nc-block") || btn.closest(".extra-nc-block") || btn.closest(".nc-detail");
    var photoInput = block.querySelector(".photo-input");
    var statusEl = block.querySelector(".ai-status");
    var descField = block.querySelector(".description-field");
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

    fetch(suggestUrl, { method: "POST", body: fd, headers: { "X-CSRFToken": csrfTokenInput.value } })
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
  }

  form.addEventListener("click", function (e) {
    var target = e.target;

    var addItemBtn = target.closest(".add-item-nc");
    if (addItemBtn) {
      var itemId = addItemBtn.dataset.itemId;
      var listEl = form.querySelector('.item-nc-list[data-item-id="' + itemId + '"]');
      var itemTotalInput = form.querySelector('input[name="item_' + itemId + '_extra-TOTAL_FORMS"]') ||
        form.querySelector('input[name="item_' + itemId + '_nc-TOTAL_FORMS"]');
      if (!itemExtraTpl || !listEl || !itemTotalInput) return;
      var index = parseInt(itemTotalInput.value, 10);
      var html = itemExtraTpl.innerHTML.replace(/__ITEMID__/g, itemId).replace(/__prefix__/g, index);
      var wrapper = document.createElement("div");
      wrapper.innerHTML = html;
      var block = wrapper.firstElementChild;
      listEl.appendChild(block);
      enhanceBlock(block);
      itemTotalInput.value = index + 1;
      refreshResponsibleSelects();
      return;
    }

    if (addExtraBtn && target.closest("#add-extra-nc")) {
      var exIndex = parseInt(extraTotalInput.value, 10);
      var exHtml = extraTpl.innerHTML.replace(/__prefix__/g, exIndex);
      var exWrapper = document.createElement("div");
      exWrapper.innerHTML = exHtml;
      var exBlock = exWrapper.firstElementChild;
      extraContainer.appendChild(exBlock);
      enhanceBlock(exBlock);
      extraTotalInput.value = exIndex + 1;
      refreshResponsibleSelects();
      return;
    }

    var removeBtn = target.closest(".remove-item-nc");
    if (removeBtn) {
      var ncBlock = removeBtn.closest(".item-nc-block") || removeBtn.closest(".extra-nc-block");
      if (ncBlock) removeNcBlock(ncBlock);
      return;
    }

    var aiBtn = target.closest(".suggest-ai-btn");
    if (aiBtn) {
      handleAiSuggest(aiBtn);
    }
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
});
