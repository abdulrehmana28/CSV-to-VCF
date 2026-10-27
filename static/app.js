(function () {
  "use strict";

  var STORAGE_KEY = "seerah-batch-code";
  var MAX_BYTES = 50 * 1024 * 1024;
  var ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".xlsm"];

  var form = document.getElementById("convert-form");
  var dropzone = document.getElementById("dropzone");
  var fileInput = document.getElementById("file-input");
  var fileChip = document.getElementById("file-chip");
  var fileName = document.getElementById("file-name");
  var fileSize = document.getElementById("file-size");
  var removeFileButton = document.getElementById("remove-file");
  var batchCodeInput = document.getElementById("batch-code");
  var nameStyleSelect = document.getElementById("name-style");
  var previewName = document.getElementById("preview-name");
  var formError = document.getElementById("form-error");
  var submitButton = document.getElementById("submit-btn");
  var buttonLabel = submitButton.querySelector(".button-label");
  var results = document.getElementById("results");
  var statRows = document.getElementById("stat-rows");
  var statContacts = document.getElementById("stat-contacts");
  var statSkipped = document.getElementById("stat-skipped");
  var batchesContainer = document.getElementById("batches");
  var skippedSummary = document.getElementById("skipped-summary");
  var skippedTableWrap = document.getElementById("skipped-table-wrap");
  var reportLink = document.getElementById("report-link");
  var resetButton = document.getElementById("reset-btn");

  var selectedFile = null;

  var nameFormats = {
    brackets: function (code, name) { return "[" + code + "] " + name; },
    dash: function (code, name) { return code + " - " + name; },
    parentheses: function (code, name) { return name + " (" + code + ")"; },
    prefix: function (code, name) { return code + " " + name; }
  };

  // ---------- small helpers ----------

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function extensionOf(filename) {
    var dot = filename.lastIndexOf(".");
    return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function plural(count, singular, pluralWord) {
    return count === 1 ? singular : (pluralWord || singular + "s");
  }

  function loadSavedCode() {
    try {
      var saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) batchCodeInput.value = saved;
    } catch (error) {
      /* localStorage can be unavailable; the app still works. */
    }
  }

  function saveCode() {
    try {
      var value = batchCodeInput.value.trim();
      if (value) window.localStorage.setItem(STORAGE_KEY, value);
    } catch (error) {
      /* ignore */
    }
  }

  function updatePreview() {
    var code = batchCodeInput.value.trim() || "SCRYK-8001";
    var style = nameStyleSelect.value;
    var formatter = nameFormats[style] || nameFormats.brackets;
    previewName.textContent = formatter(code, "Ahmed Ali");
  }

  function clearError() {
    formError.hidden = true;
    formError.replaceChildren();
  }

  function showError(message, columns) {
    formError.replaceChildren();
    formError.appendChild(element("div", null, message));

    if (columns && columns.length) {
      var list = element("ul");
      columns.slice(0, 12).forEach(function (column) {
        list.appendChild(element("li", null, column));
      });
      formError.appendChild(list);
    }

    formError.hidden = false;
    formError.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function setLoading(loading) {
    submitButton.disabled = loading;
    submitButton.classList.toggle("is-loading", loading);
    buttonLabel.textContent = loading ? "Generating…" : "Generate contact file";
  }

  // ---------- file selection ----------

  function setFile(file) {
    if (!file) return;

    var extension = extensionOf(file.name);
    if (ALLOWED_EXTENSIONS.indexOf(extension) === -1) {
      selectedFile = null;
      fileInput.value = "";
      showError("Please choose a CSV or Excel (.xlsx) file.");
      return;
    }

    if (file.size > MAX_BYTES) {
      selectedFile = null;
      fileInput.value = "";
      showError("That file is larger than 50 MB. Please choose a smaller file.");
      return;
    }

    selectedFile = file;
    clearError();
    fileName.textContent = file.name;
    fileSize.textContent = formatBytes(file.size);
    fileChip.hidden = false;
    dropzone.hidden = true;
    results.hidden = true;
  }

  function removeFile() {
    selectedFile = null;
    fileInput.value = "";
    fileChip.hidden = true;
    dropzone.hidden = false;
    dropzone.focus();
  }

  dropzone.addEventListener("click", function () {
    fileInput.click();
  });

  dropzone.addEventListener("keydown", function (event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", function () {
    if (fileInput.files && fileInput.files[0]) {
      setFile(fileInput.files[0]);
    }
  });

  removeFileButton.addEventListener("click", removeFile);

  ["dragenter", "dragover"].forEach(function (eventName) {
    dropzone.addEventListener(eventName, function (event) {
      event.preventDefault();
      event.stopPropagation();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      dropzone.classList.add("is-dragging");
    });
  });

  ["dragleave", "dragend"].forEach(function (eventName) {
    dropzone.addEventListener(eventName, function (event) {
      event.preventDefault();
      dropzone.classList.remove("is-dragging");
    });
  });

  dropzone.addEventListener("drop", function (event) {
    event.preventDefault();
    event.stopPropagation();
    dropzone.classList.remove("is-dragging");
    if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0]) {
      setFile(event.dataTransfer.files[0]);
    }
  });

  // Stop the browser from opening a file dropped outside the dropzone.
  ["dragover", "drop"].forEach(function (eventName) {
    window.addEventListener(eventName, function (event) {
      if (!dropzone.contains(event.target)) event.preventDefault();
    });
  });

  // ---------- preview ----------

  batchCodeInput.addEventListener("input", function () {
    updatePreview();
    saveCode();
  });

  nameStyleSelect.addEventListener("change", updatePreview);

  // ---------- results ----------

  function renderContactTable(contacts, limited) {
    var wrap = element("div", "table-wrap");
    var table = element("table");

    var thead = element("thead");
    var headRow = element("tr");
    headRow.appendChild(element("th", null, "Contact name"));
    headRow.appendChild(element("th", null, "WhatsApp number"));
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = element("tbody");
    contacts.forEach(function (contact) {
      var row = element("tr");
      row.appendChild(element("td", null, contact.name));
      row.appendChild(element("td", "phone-cell", contact.phone));
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);

    var fragment = document.createDocumentFragment();
    if (limited) {
      fragment.appendChild(element(
        "p",
        "contact-note",
        "Showing the first " + contacts.length + " contacts. The downloaded VCF contains every contact."
      ));
    }
    fragment.appendChild(wrap);
    return fragment;
  }

  function renderBatch(batch) {
    var card = element("article", "batch-card");

    var top = element("div", "batch-top");
    var identity = element("div");
    identity.appendChild(element("p", "batch-label", "Batch code"));
    identity.appendChild(element("div", "code-pill", batch.code));

    var meta = element(
      "p",
      "batch-meta",
      batch.contacts + " " + plural(batch.contacts, "contact") + " · " + batch.filename
    );
    identity.appendChild(meta);

    var download = element("a", "download-button", "Download VCF");
    download.href = batch.download_url;
    download.setAttribute("download", batch.filename);
    download.setAttribute("aria-label", "Download " + batch.filename);

    top.appendChild(identity);
    top.appendChild(download);
    card.appendChild(top);

    if (batch.preview && batch.preview.length) {
      var details = element("details", "contact-details");
      if (batch.contacts <= 6) details.open = true;

      var summary = element(
        "summary",
        null,
        "Preview " + batch.preview.length + " " + plural(batch.preview.length, "contact") +
          (batch.preview_limited ? " (first " + batch.preview.length + ")" : "")
      );
      details.appendChild(summary);
      details.appendChild(renderContactTable(batch.preview, batch.preview_limited));
      card.appendChild(details);
    }

    return card;
  }

  function renderSkipped(data) {
    skippedTableWrap.replaceChildren();

    if (!data.skipped_total) {
      skippedSummary.textContent = "No rows were skipped — every row with a name and valid number was included.";
      skippedTableWrap.hidden = true;
      reportLink.hidden = true;
      return;
    }

    var message = data.skipped_total + " " + plural(data.skipped_total, "row") +
      " skipped. The file was still generated with the valid contacts.";
    if (data.skipped_limited) {
      message += " Showing the first " + data.skipped.length + " below; download the report for all of them.";
    }
    skippedSummary.textContent = message;

    reportLink.hidden = false;
    reportLink.href = data.report_url;

    var table = element("table");
    var thead = element("thead");
    var headRow = element("tr");
    ["Row", "Name", "Phone", "Reason"].forEach(function (heading) {
      headRow.appendChild(element("th", null, heading));
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = element("tbody");
    data.skipped.forEach(function (item) {
      var row = element("tr");
      row.appendChild(element("td", null, item.row));
      row.appendChild(element("td", null, item.name === null || item.name === undefined || item.name === "" ? "—" : item.name));
      row.appendChild(element("td", "phone-cell", item.phone === null || item.phone === undefined || item.phone === "" ? "—" : item.phone));
      var reasonCell = element("td");
      reasonCell.appendChild(element("span", "reason-pill", item.reason));
      row.appendChild(reasonCell);
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    skippedTableWrap.appendChild(table);
    skippedTableWrap.hidden = false;
  }

  function renderResults(data) {
    statRows.textContent = Number(data.total_rows).toLocaleString();
    statContacts.textContent = Number(data.total_contacts).toLocaleString();
    statSkipped.textContent = Number(data.skipped_total).toLocaleString();

    batchesContainer.replaceChildren();
    data.batches.forEach(function (batch) {
      batchesContainer.appendChild(renderBatch(batch));
    });

    renderSkipped(data);

    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------- submit ----------

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    clearError();

    if (!selectedFile) {
      showError("Choose a CSV or Excel file first.");
      dropzone.focus();
      return;
    }

    var code = batchCodeInput.value.trim();
    saveCode();

    var params = new URLSearchParams({
      filename: selectedFile.name,
      style: nameStyleSelect.value
    });
    if (code) params.set("code", code);

    setLoading(true);

    fetch("/api/convert?" + params.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: selectedFile
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { response: response, data: data };
        }).catch(function () {
          throw new Error("The local server returned an unexpected response (" + response.status + ").");
        });
      })
      .then(function (result) {
        if (!result.response.ok || !result.data.ok) {
          var columns = result.data.columns || null;
          showError(result.data.error || "Could not generate the contact file.", columns);
          return;
        }
        renderResults(result.data);
      })
      .catch(function (error) {
        showError(
          "Could not reach the local converter. Make sure the terminal running the web app is still open. " +
          error.message
        );
      })
      .finally(function () {
        setLoading(false);
      });
  });

  // ---------- reset ----------

  resetButton.addEventListener("click", function () {
    selectedFile = null;
    fileInput.value = "";
    fileChip.hidden = true;
    dropzone.hidden = false;
    results.hidden = true;
    clearError();
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    dropzone.focus();
  });

  // ---------- init ----------

  loadSavedCode();
  updatePreview();
})();
