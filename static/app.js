/* ========================================
   Bulkognize - Frontend Logic
   ======================================== */

(function () {
    "use strict";

    // ---- Tab switching ----
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabPanels = document.querySelectorAll(".tab-content");

    tabBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
            const target = btn.dataset.tab;
            tabBtns.forEach(function (b) { b.classList.remove("active"); });
            tabPanels.forEach(function (p) { p.classList.remove("active"); });
            btn.classList.add("active");
            document.getElementById("panel-" + target).classList.add("active");
        });
    });

    // ============================================================
    //  QUICK ID
    // ============================================================

    var quickFile = null;

    var quickCamera = document.getElementById("quick-camera");
    var quickFileInput = document.getElementById("quick-file");
    var quickPreview = document.getElementById("quick-preview");
    var quickPreviewImg = document.getElementById("quick-preview-img");
    var quickSubmit = document.getElementById("quick-submit");
    var quickClear = document.getElementById("quick-clear");
    var quickLoading = document.getElementById("quick-loading");
    var quickError = document.getElementById("quick-error");
    var quickErrorMsg = document.getElementById("quick-error-msg");
    var quickErrorDismiss = document.getElementById("quick-error-dismiss");
    var quickResults = document.getElementById("quick-results");

    function handleQuickFile(file) {
        if (!file) return;
        quickFile = file;
        var reader = new FileReader();
        reader.onload = function (e) {
            quickPreviewImg.src = e.target.result;
            quickPreview.style.display = "block";
            quickSubmit.style.display = "block";
            quickResults.style.display = "none";
        };
        reader.readAsDataURL(file);
    }

    quickCamera.addEventListener("change", function () {
        handleQuickFile(this.files[0]);
    });

    quickFileInput.addEventListener("change", function () {
        handleQuickFile(this.files[0]);
    });

    quickClear.addEventListener("click", function () {
        quickFile = null;
        quickPreview.style.display = "none";
        quickSubmit.style.display = "none";
        quickCamera.value = "";
        quickFileInput.value = "";
    });

    quickErrorDismiss.addEventListener("click", function () {
        quickError.style.display = "none";
    });

    quickSubmit.addEventListener("click", function () {
        if (!quickFile) return;

        quickLoading.style.display = "block";
        quickError.style.display = "none";
        quickResults.style.display = "none";
        quickSubmit.disabled = true;

        var formData = new FormData();
        formData.append("image", quickFile);

        fetch("/api/predict", { method: "POST", body: formData })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                quickLoading.style.display = "none";
                quickSubmit.disabled = false;

                if (data.error) {
                    quickErrorMsg.textContent = data.error;
                    quickError.style.display = "flex";
                    return;
                }

                renderQuickResults(data);
            })
            .catch(function (err) {
                quickLoading.style.display = "none";
                quickSubmit.disabled = false;
                quickErrorMsg.textContent = "Could not connect to the server. Please try again.";
                quickError.style.display = "flex";
            });
    });

    function renderQuickResults(data) {
        var predictions = data.predictions || [];
        if (predictions.length === 0) {
            quickResults.innerHTML = '<div class="card no-results">No matches found. Try a clearer photo.</div>';
            quickResults.style.display = "block";
            return;
        }

        var html = '<div class="result-card">';
        html += '<div class="result-card-body">';
        html += '<div class="quick-result-layout">';
        html += '<img class="quick-uploaded-img" src="' + escapeAttr(data.uploaded_image) + '" alt="Your photo">';
        html += '<div style="flex:1">';

        predictions.forEach(function (p, i) {
            html += renderPredictionRow(p, i);
        });

        html += '</div></div></div></div>';
        quickResults.innerHTML = html;
        quickResults.style.display = "block";
        quickResults.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // ============================================================
    //  BULK UPLOAD
    // ============================================================

    var bulkFileList = [];
    var bulkFilesInput = document.getElementById("bulk-files");
    var bulkDrop = document.getElementById("bulk-drop");
    var bulkFileListEl = document.getElementById("bulk-file-list");
    var bulkSubmit = document.getElementById("bulk-submit");
    var bulkProgress = document.getElementById("bulk-progress");
    var bulkProgressText = document.getElementById("bulk-progress-text");
    var bulkProgressCount = document.getElementById("bulk-progress-count");
    var bulkProgressFill = document.getElementById("bulk-progress-fill");
    var bulkError = document.getElementById("bulk-error");
    var bulkErrorMsg = document.getElementById("bulk-error-msg");
    var bulkErrorDismiss = document.getElementById("bulk-error-dismiss");
    var bulkResults = document.getElementById("bulk-results");
    var bulkResultsList = document.getElementById("bulk-results-list");
    var bulkResultsTitle = document.getElementById("bulk-results-title");

    // Drag and drop
    ["dragenter", "dragover"].forEach(function (evt) {
        bulkDrop.addEventListener(evt, function (e) {
            e.preventDefault();
            bulkDrop.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach(function (evt) {
        bulkDrop.addEventListener(evt, function (e) {
            e.preventDefault();
            bulkDrop.classList.remove("dragover");
        });
    });

    bulkDrop.addEventListener("drop", function (e) {
        var files = e.dataTransfer.files;
        addBulkFiles(files);
    });

    bulkFilesInput.addEventListener("change", function () {
        addBulkFiles(this.files);
    });

    function addBulkFiles(files) {
        for (var i = 0; i < files.length; i++) {
            if (files[i].type.startsWith("image/")) {
                bulkFileList.push(files[i]);
            }
        }
        renderBulkFileList();
    }

    function renderBulkFileList() {
        if (bulkFileList.length === 0) {
            bulkFileListEl.style.display = "none";
            bulkSubmit.style.display = "none";
            return;
        }

        var html = "";
        bulkFileList.forEach(function (file, idx) {
            var thumbUrl = URL.createObjectURL(file);
            html += '<div class="file-list-item">';
            html += '<img class="file-thumb" src="' + thumbUrl + '" alt="">';
            html += '<span class="file-name">' + escapeHtml(file.name) + '</span>';
            html += '<button class="file-remove" data-idx="' + idx + '" title="Remove">&times;</button>';
            html += '</div>';
        });

        bulkFileListEl.innerHTML = html;
        bulkFileListEl.style.display = "block";
        bulkSubmit.style.display = "block";

        // Bind remove buttons
        bulkFileListEl.querySelectorAll(".file-remove").forEach(function (btn) {
            btn.addEventListener("click", function () {
                bulkFileList.splice(parseInt(btn.dataset.idx), 1);
                renderBulkFileList();
            });
        });
    }

    bulkErrorDismiss.addEventListener("click", function () {
        bulkError.style.display = "none";
    });

    bulkSubmit.addEventListener("click", function () {
        if (bulkFileList.length === 0) return;

        bulkError.style.display = "none";
        bulkResults.style.display = "none";
        bulkSubmit.disabled = true;

        // Show progress
        bulkProgress.style.display = "block";
        bulkProgressText.textContent = "Uploading images...";
        bulkProgressCount.textContent = "0 / " + bulkFileList.length;
        bulkProgressFill.style.width = "0%";

        // Simulate progress while waiting
        var total = bulkFileList.length;
        var fakeProgress = 0;
        var progressInterval = setInterval(function () {
            if (fakeProgress < 90) {
                fakeProgress += (90 - fakeProgress) * 0.05;
                bulkProgressFill.style.width = fakeProgress + "%";
                var estimated = Math.min(Math.floor(fakeProgress / 100 * total), total - 1);
                bulkProgressCount.textContent = estimated + " / " + total;
                bulkProgressText.textContent = "Identifying minifigs...";
            }
        }, 500);

        var formData = new FormData();
        bulkFileList.forEach(function (file) {
            formData.append("images", file);
        });

        fetch("/api/bulk", { method: "POST", body: formData })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                clearInterval(progressInterval);
                bulkProgressFill.style.width = "100%";
                bulkProgressCount.textContent = total + " / " + total;
                bulkProgressText.textContent = "Done!";

                setTimeout(function () {
                    bulkProgress.style.display = "none";
                    bulkSubmit.disabled = false;

                    if (data.error) {
                        bulkErrorMsg.textContent = data.error;
                        bulkError.style.display = "flex";
                        return;
                    }

                    renderBulkResults(data);
                }, 600);
            })
            .catch(function (err) {
                clearInterval(progressInterval);
                bulkProgress.style.display = "none";
                bulkSubmit.disabled = false;
                bulkErrorMsg.textContent = "Could not connect to the server. Please try again.";
                bulkError.style.display = "flex";
            });
    });

    function renderBulkResults(data) {
        var results = data.results || [];
        var errors = data.errors || [];

        if (results.length === 0 && errors.length === 0) {
            bulkResultsList.innerHTML = '<div class="card no-results">No results. Try different images.</div>';
            bulkResults.style.display = "block";
            return;
        }

        bulkResultsTitle.textContent = "Results (" + results.length + " images)";
        var html = "";

        results.forEach(function (result) {
            html += '<div class="result-card">';
            html += '<div class="result-card-header">';
            html += '<img class="bulk-source-img" src="' + escapeAttr(result.uploaded_image) + '" alt="" style="vertical-align:middle; margin-right:10px;">';
            html += escapeHtml(result.filename);
            html += '</div>';
            html += '<div class="result-card-body">';

            if (result.predictions.length === 0) {
                html += '<p class="no-results">No matches found</p>';
            } else {
                result.predictions.forEach(function (p, i) {
                    html += renderPredictionRow(p, i);
                });
            }

            html += '</div></div>';
        });

        // Show errors if any
        if (errors.length > 0) {
            html += '<div class="card card-error" style="display:block">';
            html += '<p><strong>Some images had errors:</strong></p>';
            errors.forEach(function (e) {
                html += '<p>' + escapeHtml(e.filename) + ': ' + escapeHtml(e.error) + '</p>';
            });
            html += '</div>';
        }

        bulkResultsList.innerHTML = html;
        bulkResults.style.display = "block";

        // Reset file list for next batch
        bulkFileList = [];
        renderBulkFileList();
        bulkFilesInput.value = "";

        bulkResults.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // ============================================================
    //  SHARED HELPERS
    // ============================================================

    function renderPredictionRow(p, index) {
        var scoreClass = p.score >= 50 ? "badge-score" : "badge-score low";
        var html = '<div class="prediction-row">';

        if (p.img_url) {
            html += '<img class="prediction-thumb" src="' + escapeAttr(p.img_url) + '" alt="" loading="lazy">';
        }

        html += '<div class="prediction-info">';
        html += '<div class="prediction-name">' + escapeHtml(p.name) + '</div>';
        html += '<div class="prediction-id">' + escapeHtml(p.id) + (p.type ? ' &middot; ' + escapeHtml(p.type) : '') + '</div>';
        html += '<div class="prediction-meta">';
        html += '<span class="badge ' + scoreClass + '">' + p.score + '%</span>';

        if (p.category) {
            html += '<span class="badge badge-category">' + escapeHtml(p.category) + '</span>';
        }

        if (p.bricklink_url) {
            html += '<a class="bricklink-btn" href="' + escapeAttr(p.bricklink_url) + '" target="_blank" rel="noopener">BrickLink</a>';
        }

        html += '</div></div></div>';
        return html;
    }

    function escapeHtml(str) {
        if (!str) return "";
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeAttr(str) {
        if (!str) return "";
        return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // ============================================================
    //  SERVICE WORKER REGISTRATION
    // ============================================================

    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("/static/sw.js").catch(function () {
            // Service worker registration failed silently - app still works fine
        });
    }

})();
