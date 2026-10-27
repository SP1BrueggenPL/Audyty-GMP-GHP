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
  var DRAFT_MODE = form.dataset.autosave === "1";
  var uploadUrl = form.dataset.uploadUrl;
  var photoDeleteUrl = form.dataset.photoDeleteUrl;
  var moveUrl = form.dataset.moveUrl;

  // ---- 0) Jedna kolejka żądań zapisu -----------------------------------------
  // Autozapis tekstu i wysyłka zdjęć idą PO KOLEI, nigdy równolegle - dzięki temu
  // id niezgodności zwrócone przez serwer trafia do formularza, zanim wystartuje
  // następne żądanie (równoległe żądania mogłyby utworzyć tę samą niezgodność dwa razy).
  var netQueue = Promise.resolve();
  var netPending = 0;
  function enqueue(task) {
    netPending++;
    netQueue = netQueue.then(task).catch(function () {}).then(function () { netPending--; });
    return netQueue;
  }
  function whenIdle() {
    return netQueue.then(function () { return netPending > 0 ? whenIdle() : null; });
  }
  function csrfToken() {
    var el = form.querySelector('input[name="csrfmiddlewaretoken"]');
    return el ? el.value : "";
  }
  function fieldValue(name) {
    var el = form.querySelector('[name="' + name + '"]');
    return el ? el.value : "";
  }
  function readJson(response) {
    return response.json().then(
      function (data) { return { status: response.status, data: data }; },
      function () {
        return {
          status: response.status,
          data: {
            ok: false, saved: false,
            error: "Serwer zwrócił nieoczekiwaną odpowiedź (HTTP " + response.status + "). " +
              "Sesja mogła wygasnąć - odśwież stronę i zaloguj się ponownie (dane i zdjęcia zapisane wcześniej zostają).",
          },
        };
      }
    );
  }

  // ---- 1a) Zdjęcia niezgodności (max 10) ---------------------------------------
  // WERSJA ROBOCZA (draft): każde zdjęcie jest wysyłane na serwer OD RAZU po
  // zrobieniu, osobnym, małym żądaniem - z widocznym statusem przy miniaturze,
  // automatycznym ponawianiem po utracie połączenia i ręcznym przyciskiem "Ponów".
  // Zdjęcie jest zapisane w inspekcji (i w galerii aplikacji) zanim audytor
  // zacznie robić następne - nic nie czeka "na koniec w jednym wielkim zapisie".
  function photoSlot(input) {
    var m = /^(item_(\d+)_nc-(\d+))-photos$/.exec(input.name);
    if (m) return { kind: "item", itemId: m[2], prefix: m[1] };
    m = /^(extra-(\d+))-photos$/.exec(input.name);
    if (m) return { kind: "extra", itemId: "", prefix: m[1] };
    return null;
  }

  function downloadFiles(files) {
    files.forEach(function (f) {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(f);
      a.download = f.name || "zdjecie.jpg";
      document.body.appendChild(a);
      a.click();
      a.remove();
    });
  }

  function enhancePhotoInputDraft(input) {
    var slot = photoSlot(input);
    if (!slot || !uploadUrl) return false;
    function existingCount() { return parseInt(input.dataset.existingPhotos || "0", 10) || 0; }
    var entries = [];
    input._entries = entries;

    var wrap = document.createElement("div");
    wrap.className = "photo-upload-wrap";
    input.insertAdjacentElement("afterend", wrap);
    var thumbsEl = document.createElement("div");
    thumbsEl.className = "photo-thumbs";
    var countEl = document.createElement("div");
    countEl.className = "muted photo-count";
    var shareRow = document.createElement("div");
    shareRow.className = "photo-share-row";
    var shareBtn = document.createElement("button");
    shareBtn.type = "button";
    shareBtn.className = "btn btn-outline btn-sm";
    shareBtn.textContent = "💾 Zapisz kopię w galerii urządzenia";
    var shareHint = document.createElement("span");
    shareHint.className = "muted";
    shareHint.style.marginLeft = ".5rem";
    shareHint.textContent = "w oknie udostępniania wybierz „Zapisz obraz” (przeglądarka nie pozwala zrobić tego automatycznie)";
    shareRow.appendChild(shareBtn);
    shareRow.appendChild(shareHint);
    wrap.appendChild(thumbsEl);
    wrap.appendChild(countEl);
    wrap.appendChild(shareRow);

    function render() {
      thumbsEl.innerHTML = "";
      var saved = 0;
      entries.forEach(function (entry) {
        if (entry.status === "saved") saved++;
        var item = document.createElement("div");
        item.className = "photo-thumb is-" + entry.status;
        var img = document.createElement("img");
        img.src = entry.serverUrl || entry.url;
        item.appendChild(img);

        var badge = document.createElement("div");
        badge.className = "photo-badge";
        badge.textContent = entry.status === "saved" ? "✓ zapisane"
          : entry.status === "error" ? "⚠ nie zapisane" : "⟳ zapisuję…";
        item.appendChild(badge);

        if (entry.status === "error") {
          var msg = document.createElement("div");
          msg.className = "photo-error";
          msg.textContent = entry.error || "Nie udało się zapisać.";
          item.appendChild(msg);
          var retry = document.createElement("button");
          retry.type = "button";
          retry.className = "photo-retry";
          retry.textContent = "↻ Ponów";
          retry.addEventListener("click", function () { entry.attempts = 0; upload(entry); });
          item.appendChild(retry);
        }

        var rm = document.createElement("button");
        rm.type = "button";
        rm.className = "photo-thumb-remove";
        rm.textContent = "✕";
        rm.addEventListener("click", function () { removeEntry(entry); });
        item.appendChild(rm);
        thumbsEl.appendChild(item);
      });
      countEl.textContent = (existingCount() + entries.length) + " / " + MAX_PHOTOS + " zdjęć" +
        (entries.length ? " · zapisane w inspekcji: " + saved + " z " + entries.length + " nowych" : "");
      shareRow.style.display = entries.length ? "" : "none";
    }

    function fail(entry, status, message) {
      entry.status = "error";
      entry.error = message || "Nie udało się zapisać zdjęcia.";
      // Błędy sieci/serwera (5xx) ponawiamy same; błędy 4xx (np. plik odrzucony) - tylko ręcznie.
      var retryable = status === 0 || status >= 500;
      var delays = [3000, 8000, 20000];
      if (retryable && entry.attempts < delays.length) {
        var delay = delays[entry.attempts];
        entry.attempts++;
        setTimeout(function () {
          if (!entry.cancelled && entry.status === "error") upload(entry);
        }, delay);
      }
    }

    function upload(entry) {
      entry.status = "queued";
      render();
      enqueue(function () {
        if (entry.cancelled || !document.body.contains(input)) return null;
        entry.status = "uploading";
        render();

        var fd = new FormData();
        fd.append("photo", entry.file, entry.file.name || "foto.jpg");
        fd.append("kind", slot.kind);
        var idField = form.querySelector('input[name="' + slot.prefix + '-id"]');
        if (idField && idField.value) fd.append("nc_id", idField.value);
        fd.append("item_id", slot.kind === "item" ? slot.itemId : fieldValue(slot.prefix + "-item"));
        fd.append("description", fieldValue(slot.prefix + "-description"));
        fd.append("location", fieldValue(slot.prefix + "-location"));
        fd.append("responsible", fieldValue(slot.prefix + "-responsible"));

        return fetch(uploadUrl, {
          method: "POST", body: fd, headers: { "X-CSRFToken": csrfToken() }, credentials: "same-origin",
        })
          .then(readJson)
          .then(function (res) {
            if (res.data.ok) {
              if (idField) idField.value = res.data.nc_id;
              entry.status = "saved";
              entry.photoId = res.data.photo_id;
              entry.serverUrl = res.data.url;
            } else {
              fail(entry, res.status, res.data.error);
            }
          })
          .catch(function () { fail(entry, 0, "Brak połączenia - zdjęcie zostanie wysłane ponownie."); })
          .then(render);
      });
    }

    function removeEntry(entry) {
      if (entry.status === "saved" && entry.photoId) {
        if (!confirm("Usunąć to zdjęcie z inspekcji?")) return;
        enqueue(function () {
          return fetch(photoDeleteUrl.replace("/0/", "/" + entry.photoId + "/"), {
            method: "POST", headers: { "X-CSRFToken": csrfToken() }, credentials: "same-origin",
          })
            .then(readJson)
            .then(function (res) {
              if (res.data.ok) {
                entries.splice(entries.indexOf(entry), 1);
              } else {
                alert(res.data.error || "Nie udało się usunąć zdjęcia.");
              }
              render();
            })
            .catch(function () { alert("Brak połączenia - nie udało się usunąć zdjęcia."); });
        });
        return;
      }
      entry.cancelled = true;
      entries.splice(entries.indexOf(entry), 1);
      render();
    }

    shareBtn.addEventListener("click", function () {
      var files = entries.map(function (e) { return e.file; }).filter(Boolean);
      if (!files.length) return;
      if (navigator.share && navigator.canShare && navigator.canShare({ files: files })) {
        navigator.share({ files: files }).catch(function (err) {
          if (err && err.name !== "AbortError") downloadFiles(files);
        });
      } else {
        downloadFiles(files);
      }
    });

    input.addEventListener("change", function () {
      var incoming = Array.prototype.slice.call(input.files || []);
      input.value = ""; // pliki przejmuje lista "entries" - pole zostaje puste, żeby ten sam plik dało się wybrać ponownie
      var room = MAX_PHOTOS - existingCount() - entries.length;
      if (incoming.length > room) {
        alert("Można dodać maksymalnie " + MAX_PHOTOS + " zdjęć do jednej niezgodności.");
      }
      incoming.slice(0, Math.max(room, 0)).forEach(function (f) {
        var entry = { file: f, url: URL.createObjectURL(f), status: "queued", attempts: 0 };
        entries.push(entry);
        upload(entry);
      });
      render();
    });

    input._render = render;

    // Do podpowiedzi AI - pierwsze zdjęcie z tego pola (pole "files" jest puste).
    input._firstFile = function () {
      var e = entries.filter(function (x) { return x.file; })[0];
      return e ? e.file : null;
    };

    render();
    return true;
  }

  // WERSJA ZAPISANA (edycja ukończonej inspekcji): zwykły formularz - akumulator
  // plików (kolejne wywołania aparatu NADPISUJĄ selekcję w input[type=file], więc
  // zbieramy je w tablicy i odtwarzamy input.files przez DataTransfer).
  function enhancePhotoInputLegacy(input) {
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

  function enhancePhotoInput(input) {
    if (input.dataset.photoEnhanced === "1") return;
    input.dataset.photoEnhanced = "1";
    if (DRAFT_MODE && enhancePhotoInputDraft(input)) return;
    enhancePhotoInputLegacy(input);
  }

  // ---- 1b) Dyktowanie opisu niezgodności (Web Speech API) ----------------
  // Brak wsparcia w przeglądarce (np. Firefox) - po prostu nie dodajemy
  // przycisku, reszta formularza działa normalnie.
  var SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;

  // iPhone/iPad (także w Edge/Chrome - na iOS wszystkie przeglądarki używają silnika
  // Safari): dyktowanie z poziomu strony jest tam zawodne (sesja kończy się kodem
  // "aborted"), a wbudowane dyktowanie z klawiatury działa w każdym polu - dlatego
  // zamiast przycisku pokazujemy podpowiedź. iPadOS podaje się jako Macintosh,
  // stąd dodatkowy test ekranu dotykowego.
  var IS_IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

  function enhanceMic(descField) {
    if (descField.dataset.micEnhanced === "1") return;
    descField.dataset.micEnhanced = "1";

    if (IS_IOS) {
      var hint = document.createElement("div");
      hint.className = "mic-status muted";
      hint.style.marginTop = ".25rem";
      hint.textContent = "🎤 Dyktowanie: dotknij ikony mikrofonu na klawiaturze iPada (jeśli jej nie ma: " +
        "Ustawienia → Ogólne → Klawiatura → Włącz dyktowanie).";
      descField.insertAdjacentElement("afterend", hint);
      return;
    }
    if (!SpeechRecognitionCtor) return;

    var micBtn = document.createElement("button");
    micBtn.type = "button";
    micBtn.className = "btn btn-outline btn-sm mic-btn";
    micBtn.textContent = "🎤 Dyktuj opis";
    descField.insertAdjacentElement("afterend", micBtn);

    var micStatus = document.createElement("span");
    micStatus.className = "mic-status muted";
    micStatus.style.marginLeft = ".5rem";
    micBtn.insertAdjacentElement("afterend", micStatus);

    var MIC_ERROR_MESSAGES = {
      "not-allowed": "Brak zgody na mikrofon - sprawdź uprawnienia aplikacji/przeglądarki dla mikrofonu w ustawieniach tabletu.",
      "service-not-allowed": "Brak zgody na mikrofon - sprawdź uprawnienia aplikacji/przeglądarki dla mikrofonu w ustawieniach tabletu.",
      "no-speech": "Nie wykryto mowy - spróbuj ponownie bliżej mikrofonu.",
      "audio-capture": "Nie znaleziono mikrofonu na tym urządzeniu.",
      "network": "Brak połączenia z internetem - dyktowanie wymaga sieci.",
      "aborted": "",
    };

    // Chrome na Androidzie ignoruje "continuous" i kończy rozpoznawanie po
    // pierwszej frazie/pauzie (zdarzenie "end"). Dlatego "wantListening"
    // oznacza zamiar użytkownika (do kliknięcia "Zatrzymaj"), a po każdym "end"
    // przy aktywnym zamiarze sesję startujemy od nowa.
    var recognition = new SpeechRecognitionCtor();
    recognition.lang = "pl-PL";
    recognition.interimResults = false;
    recognition.continuous = false; // krótkie sesje + nasze wznawianie są stabilniejsze na tabletach
    var wantListening = false;
    var lastStartAt = 0;
    var quickEnds = 0;
    var FATAL_ERRORS = ["not-allowed", "service-not-allowed", "audio-capture", "network"];

    function setUi(active) {
      micBtn.textContent = active ? "⏹ Zatrzymaj dyktowanie" : "🎤 Dyktuj opis";
      micBtn.classList.toggle("mic-active", active);
    }

    function startRecognition() {
      lastStartAt = Date.now();
      recognition.start();
    }

    function giveUp(message) {
      wantListening = false;
      setUi(false);
      micStatus.textContent = message;
    }

    recognition.addEventListener("result", function (e) {
      var transcript = "";
      for (var i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) transcript += e.results[i][0].transcript;
      }
      transcript = transcript.trim();
      if (transcript) {
        descField.value = (descField.value ? descField.value.replace(/\s+$/, "") + " " : "") + transcript;
        descField.dispatchEvent(new Event("input", { bubbles: true })); // uruchamia autozapis
        micStatus.textContent = "";
      }
    });

    var gotAudio = false;
    var lastError = "";
    recognition.addEventListener("audiostart", function () { gotAudio = true; });

    recognition.addEventListener("end", function () {
      if (!wantListening) {
        setUi(false);
        return;
      }
      quickEnds = (Date.now() - lastStartAt < 800) ? quickEnds + 1 : 0;
      if (quickEnds >= 3) {
        giveUp(
          "Dyktowanie przerywa się od razu po uruchomieniu (" +
          (gotAudio ? "mikrofon działa, ale usługa rozpoznawania mowy kończy sesję" : "przeglądarka nie uruchomiła mikrofonu") +
          (lastError ? ", kod: " + lastError : "") + "). " +
          "Ta przeglądarka najpewniej nie obsługuje dyktowania na tym urządzeniu - użyj ikony mikrofonu na klawiaturze ekranowej tabletu."
        );
        return;
      }
      setTimeout(function () {
        if (!wantListening) return;
        try { startRecognition(); } catch (err) { giveUp("Nie udało się wznowić dyktowania."); }
      }, 500);
    });

    recognition.addEventListener("error", function (e) {
      lastError = e.error;
      if (FATAL_ERRORS.indexOf(e.error) !== -1) {
        giveUp(MIC_ERROR_MESSAGES[e.error]);
      }
      // "no-speech"/"aborted": zwykła cisza lub przerwanie sesji - po "end" wznawiamy.
    });

    function beginListening() {
      quickEnds = 0;
      gotAudio = false;
      lastError = "";
      try {
        wantListening = true;
        startRecognition();
        setUi(true);
      } catch (err) {
        giveUp("Nie udało się uruchomić mikrofonu na tym urządzeniu.");
      }
    }

    micBtn.addEventListener("click", function () {
      if (wantListening) {
        wantListening = false;
        setUi(false);
        try { recognition.stop(); } catch (err) { /* sesja już zakończona */ }
        return;
      }
      micStatus.textContent = "";
      // Jawne żądanie dostępu do mikrofonu - pokazuje systemowe pytanie o zgodę
      // i pozwala odróżnić odmowę uprawnień od problemu z samą usługą rozpoznawania.
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        navigator.mediaDevices.getUserMedia({ audio: true })
          .then(function (stream) {
            stream.getTracks().forEach(function (t) { t.stop(); });
            beginListening();
          })
          .catch(function (err) {
            giveUp(
              err && (err.name === "NotAllowedError" || err.name === "SecurityError")
                ? MIC_ERROR_MESSAGES["not-allowed"]
                : "Nie udało się uzyskać dostępu do mikrofonu (" + (err && err.name) + ")."
            );
          });
      } else {
        beginListening();
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
    var idField = block.querySelector('input[type="hidden"][name$="-id"]');
    if (idField && idField.value) {
      var deleted = document.getElementById("delete-nc-ids");
      if (deleted) deleted.value = deleted.value ? deleted.value + "," + idField.value : idField.value;
    }
    block.remove();
    scheduleAutosave(1000);
  }

  // Okno z własnymi przyciskami (confirm() pozwala tylko na OK/Anuluj bez opisu akcji).
  function askChoice(title, text, buttons) {
    return new Promise(function (resolve) {
      var overlay = document.createElement("div");
      overlay.className = "choice-overlay";
      var box = document.createElement("div");
      box.className = "choice-box";
      box.setAttribute("role", "dialog");
      box.setAttribute("aria-modal", "true");
      var h = document.createElement("h3");
      h.textContent = title;
      var p = document.createElement("p");
      p.className = "choice-text";
      p.style.whiteSpace = "pre-line";
      p.textContent = text;
      var actions = document.createElement("div");
      actions.className = "choice-actions";
      buttons.forEach(function (b) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn " + (b.primary ? "btn-primary" : "btn-outline");
        btn.textContent = b.label;
        btn.addEventListener("click", function () { overlay.remove(); resolve(b.value); });
        actions.appendChild(btn);
      });
      box.appendChild(h);
      box.appendChild(p);
      box.appendChild(actions);
      overlay.appendChild(box);
      document.body.appendChild(overlay);
    });
  }

  // AI wskazało, że zdjęcie pasuje do innego punktu: audytor wybiera - przenieść opis
  // i zdjęcia automatycznie albo zostawić tak, jak jest. Przenoszenie działa w wersji
  // roboczej (po zapisaniu wszystkiego strona odświeża się na właściwym punkcie).
  function handleMismatch(data, photoInput, statusEl) {
    var canMove = DRAFT_MODE && moveUrl && data.mismatch_item_id;
    var text = "AI sugeruje, że to zdjęcie dotyczy punktu:\n" + data.mismatch_point +
      (data.mismatch_reason ? "\n\nUzasadnienie: " + data.mismatch_reason : "");
    var buttons = [];
    if (canMove) buttons.push({ value: "move", primary: true, label: "Przenieś opis i zdjęcie do tego punktu" });
    buttons.push({ value: "stay", primary: false, label: canMove ? "Zostaw w obecnym punkcie" : "Rozumiem" });
    askChoice("Zdjęcie chyba nie pasuje do tego punktu", text, buttons).then(function (choice) {
      if (choice === "move") moveToPoint(photoInput, data.mismatch_item_id, statusEl);
      else statusEl.textContent = "Zostawiono w obecnym punkcie.";
    });
  }

  function moveToPoint(photoInput, targetItemId, statusEl) {
    var slot = photoSlot(photoInput);
    if (!slot || slot.kind !== "item") {
      statusEl.textContent = "Tej niezgodności nie można przenieść automatycznie.";
      return;
    }
    statusEl.textContent = "Przenoszę niezgodność…";
    requestAutosave(); // zapisuje opis wstawiony przez AI, zanim niezgodność zmieni punkt
    whenIdle().then(function () {
      var idField = form.querySelector('input[name="' + slot.prefix + '-id"]');
      if (!idField || !idField.value) {
        statusEl.textContent = "Poczekaj, aż zdjęcie się zapisze, i spróbuj ponownie.";
        return null;
      }
      var fd = new FormData();
      fd.append("nc_id", idField.value);
      fd.append("target_item_id", targetItemId);
      fd.append("description", fieldValue(slot.prefix + "-description"));
      return fetch(moveUrl, {
        method: "POST", body: fd, headers: { "X-CSRFToken": csrfToken() }, credentials: "same-origin",
      })
        .then(readJson)
        .then(function (res) {
          if (res.data.ok) {
            location.hash = "item-" + targetItemId;
            location.reload();
          } else {
            statusEl.textContent = res.data.error || "Nie udało się przenieść niezgodności.";
          }
        })
        .catch(function () { statusEl.textContent = "Brak połączenia - niezgodność nie została przeniesiona."; });
    });
  }

  // Usunięcie zdjęcia, które jest już zapisane na serwerze (np. po wznowieniu wersji roboczej
  // albo przy edycji ukończonej inspekcji) - przycisk ✕ na miniaturze, na wypadek pomyłki.
  function deleteExistingPhoto(btn) {
    if (!confirm("Usunąć to zdjęcie z inspekcji? Tej operacji nie można cofnąć.")) return;
    btn.disabled = true;
    fetch(photoDeleteUrl.replace("/0/", "/" + btn.dataset.photoId + "/"), {
      method: "POST", headers: { "X-CSRFToken": csrfToken() }, credentials: "same-origin",
    })
      .then(readJson)
      .then(function (res) {
        if (!res.data.ok) {
          btn.disabled = false;
          alert(res.data.error || "Nie udało się usunąć zdjęcia.");
          return;
        }
        var field = btn.closest(".field");
        var input = field && field.querySelector(".photo-input");
        var holder = btn.closest(".existing-photo");
        if (holder) holder.remove();
        if (input) {
          input.dataset.existingPhotos = Math.max(0, (parseInt(input.dataset.existingPhotos || "0", 10) || 0) - 1);
          if (input._render) input._render();
        }
      })
      .catch(function () {
        btn.disabled = false;
        alert("Brak połączenia - zdjęcie nie zostało usunięte.");
      });
  }

  function handleAiSuggest(btn) {
    var block = btn.closest(".item-nc-block") || btn.closest(".extra-nc-block") || btn.closest(".nc-detail");
    var photoInput = block.querySelector(".photo-input");
    var statusEl = block.querySelector(".ai-status");
    var descField = block.querySelector(".description-field");
    var listEl = btn.closest(".item-nc-list");
    var itemId = (listEl && listEl.dataset.itemId) || btn.dataset.itemId || (photoInput && photoInput.dataset.itemId) || "";

    var firstPhoto = (photoInput && photoInput._firstFile && photoInput._firstFile()) ||
      (photoInput && photoInput.files && photoInput.files[0]) || null;
    if (!firstPhoto) {
      statusEl.textContent = "Najpierw zrób zdjęcie niezgodności (w tej karcie przeglądarki).";
      return;
    }

    var fd = new FormData();
    fd.append("item_id", itemId);
    fd.append("photo", firstPhoto);

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
          handleMismatch(data, photoInput, statusEl);
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

    var removeExistingBtn = target.closest(".existing-photo-remove");
    if (removeExistingBtn) {
      deleteExistingPhoto(removeExistingBtn);
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

  // ---- 4) Autozapis wersji roboczej ---------------------------------------
  // Tylko dla formularza wersji roboczej (data-autosave="1"). Cały tekst formularza
  // (bez zdjęć - te idą osobno, patrz 1a) wysyła się okresowo z flagą autosave=1.
  // Serwer aktualizuje istniejące niezgodności po ukrytych polach "...-id" i zwraca
  // ich id; JS wpisuje je do formularza, żeby KOLEJNY zapis zaktualizował te same
  // rekordy. Autozapis niczego nie kasuje z domysłu (usuwa tylko jawnie usunięte -
  // pole delete_nc_ids), więc ewentualny błąd nie może skasować zdjęć.
  var autosaveStatusEl = document.getElementById("autosave-status");
  var autosaveTimer = null;
  var autosaveScheduled = false;

  function setAutosaveStatus(text) {
    if (autosaveStatusEl) autosaveStatusEl.textContent = text;
  }

  function doAutosave() {
    var fd = new FormData(form);
    fd.set("autosave", "1");
    setAutosaveStatus("Zapisywanie…");
    return fetch(window.location.href, {
      method: "POST", body: fd, headers: { "X-CSRFToken": csrfToken() }, credentials: "same-origin",
    })
      .then(readJson)
      .then(function (res) {
        var data = res.data;
        if (data.saved) {
          Object.keys(data.item_nc_ids || {}).forEach(function (itemId) {
            var forItem = data.item_nc_ids[itemId];
            Object.keys(forItem).forEach(function (i) {
              var idField = form.querySelector('input[name="item_' + itemId + '_nc-' + i + '-id"]');
              if (idField) idField.value = forItem[i];
            });
          });
          Object.keys(data.extra_nc_ids || {}).forEach(function (i) {
            var idField = form.querySelector('input[name="extra-' + i + '-id"]');
            if (idField) idField.value = data.extra_nc_ids[i];
          });
          setAutosaveStatus("Zapisano automatycznie o " + data.saved_at + ".");
        } else if (data.error) {
          setAutosaveStatus("Nie udało się zapisać: " + data.error);
        } else {
          setAutosaveStatus("Uzupełnij datę i obszar inspekcji, aby włączyć autozapis.");
        }
      })
      .catch(function () {
        setAutosaveStatus("Brak połączenia - spróbuję zapisać ponownie za chwilę.");
      });
  }

  function requestAutosave() {
    if (autosaveScheduled) return;
    autosaveScheduled = true;
    enqueue(function () {
      autosaveScheduled = false;
      return doAutosave();
    });
  }

  function scheduleAutosave(delayMs) {
    if (!DRAFT_MODE) return;
    if (autosaveTimer) clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(requestAutosave, delayMs);
  }

  function photosNotSaved() {
    var bad = [];
    form.querySelectorAll(".photo-input").forEach(function (inp) {
      (inp._entries || []).forEach(function (e) { if (e.status !== "saved") bad.push(e); });
    });
    return bad;
  }

  if (DRAFT_MODE) {
    form.addEventListener("input", function () { scheduleAutosave(4000); });
    form.addEventListener("change", function () { scheduleAutosave(2000); });
    setInterval(function () { scheduleAutosave(0); }, 45000);

    // "Zakończ inspekcję": najpierw poczekaj, aż wszystkie zdjęcia i zapisy się skończą -
    // inaczej zdjęcie, które jeszcze się wysyła, zginęłoby przy przejściu na kolejną stronę.
    form.addEventListener("submit", function (e) {
      if (form.dataset.submitReady === "1") return;
      e.preventDefault();
      setAutosaveStatus("Czekam, aż zapiszą się wszystkie zdjęcia…");
      whenIdle().then(function () {
        var bad = photosNotSaved();
        if (bad.length) {
          setAutosaveStatus("");
          alert(bad.length + " zdjęć nie zostało jeszcze zapisanych (czerwone miniatury). " +
            "Kliknij „Ponów” przy każdym z nich albo usuń je (✕), a potem zakończ inspekcję.");
          return;
        }
        form.dataset.submitReady = "1";
        form.submit();
      });
    });

    window.addEventListener("beforeunload", function (e) {
      if (photosNotSaved().length || netPending > 0) {
        e.preventDefault();
        e.returnValue = "";
      }
    });
  }
});
