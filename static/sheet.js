(function () {
  "use strict";

  var MAX_BYTES = 50 * 1024 * 1024;
  var ALLOWED_EXTENSIONS = [".vcf"];

  var form = document.getElementById("sheet-form");
  var dropzone = document.getElementById("sheet-dropzone");
  var fileInput = document.getElementById("sheet-file-input");
  var fileChip = document.getElementById("sheet-file-chip");
  var fileName = document.getElementById("sheet-file-name");
  var fileSize = document.getElementById("sheet-file-size");
  var removeFileButton = document.getElementById("sheet-remove-file");
  var formError = document.getElementById("sheet-form-error");
  var submitButton = document.getElementById("sheet-submit-btn");
  var buttonLabel = submitButton.querySelector(".button-label");
  var results = document.getElementById("sheet-results");
  var statContacts = document.getElementById("sheet-stat-contacts");
  var statRows = document.getElementById("sheet-stat-rows");
  var statSkipped = document.getElementById("sheet-stat-skipped");
  var outputName = document.getElementById("sheet-output-name");
  var outputMeta = document.getElementById("sheet-output-meta");
  var downloadLink = document.getElementById("sheet-download-link");
  var previewSummary = document.getElementById("sheet-preview-summary");
  var previewWrap = document.getElementById("sheet-preview-wrap");
  var skippedPanel = document.getElementById("sheet-skipped-panel");
  var skippedSummary = document.getElementById("sheet-skipped-summary");
  var skippedWrap = document.getElementById("sheet-skipped-wrap");
  var resetButton = document.getElementById("sheet-reset-btn");

  var selectedFile = null;
  var rowKeys = ["name", "phone", "phone_called", "is_received", "reason"];

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

  function clearError() {
    formError.hidden = true;
    formError.replaceChildren();
  }

  function showError(message) {
    formError.replaceChildren();
    formError.appendChild(element("div", null, message));
    formError.hidden = false;
    formError.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function setLoading(loading) {
    submitButton.disabled = loading;
    submitButton.classList.toggle("is-loading", loading);
    buttonLabel.textContent = loading ? "Generating…" : "Generate call sheet";
  }

  // ---------- file selection ----------

  function setFile(file) {
    if (!file) return;

    var extension = extensionOf(file.name);
    if (ALLOWED_EXTENSIONS.indexOf(extension) === -1) {
      selectedFile = null;
      fileInput.value = "";
      showError("Please choose a .vcf contact file.");
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

  // ---------- results ----------

  function renderPreview(rows, columns, limited) {
    previewWrap.replaceChildren();

    var table = element("table");
    var thead = element("thead");
    var headRow = element("tr");
    columns.forEach(function (heading) {
      headRow.appendChild(element("th", null, heading));
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = element("tbody");
    rows.forEach(function (item) {
      var row = element("tr");
      rowKeys.forEach(function (key) {
        var value = item[key];
        var shown = value === null || value === undefined || value === "" ? "—" : value;
        row.appendChild(element("td", key === "phone" ? "phone-cell" : null, shown));
      });
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    previewWrap.appendChild(table);
    previewWrap.hidden = false;

    previewSummary.textContent = "Preview " + rows.length + " " +
      plural(rows.length, "contact") + (limited ? " (first " + rows.length + ")" : "");
  }

  function renderSkipped(data) {
    skippedWrap.replaceChildren();

    if (!data.skipped_total) {
      skippedPanel.hidden = true;
      return;
    }

    var message = data.skipped_total + " " + plural(data.skipped_total, "contact") +
      " skipped because no phone number was found.";
    if (data.skipped_limited) {
      message += " Showing the first " + data.skipped.length + " below.";
    }
    skippedSummary.textContent = message;

    var table = element("table");
    var thead = element("thead");
    var headRow = element("tr");
    ["Contact", "Name", "Reason"].forEach(function (heading) {
      headRow.appendChild(element("th", null, heading));
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = element("tbody");
    data.skipped.forEach(function (item) {
      var row = element("tr");
      row.appendChild(element("td", null, item.contact));
      row.appendChild(element("td", null, item.name || "—"));
      row.appendChild(element("td", null, item.reason));
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    skippedWrap.appendChild(table);
    skippedWrap.hidden = false;
    skippedPanel.hidden = false;
  }

  function renderResults(data) {
    statContacts.textContent = Number(data.total_contacts).toLocaleString();
    statRows.textContent = Number(data.total_rows).toLocaleString();
    statSkipped.textContent = Number(data.skipped_total).toLocaleString();

    outputName.textContent = data.filename;
    outputMeta.textContent = data.total_rows + " " + plural(data.total_rows, "contact") +
      " ready · CSV for Google Sheets";
    downloadLink.href = data.download_url;
    downloadLink.setAttribute("download", data.filename);

    renderPreview(data.preview, data.columns, data.preview_limited);
    renderSkipped(data);

    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------- submit ----------

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    clearError();

    if (!selectedFile) {
      showError("Choose a .vcf file first.");
      dropzone.focus();
      return;
    }

    var params = new URLSearchParams({ filename: selectedFile.name });
    setLoading(true);

    fetch("/api/vcf-to-sheet?" + params.toString(), {
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
          showError(result.data.error || "Could not generate the call sheet.");
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
})();
