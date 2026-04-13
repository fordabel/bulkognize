/* ========================================
   Bulkognize - Frontend Logic
   ======================================== */

(function () {
    "use strict";

    // ============================================================
    //  BULK UPLOAD (with camera support)
    // ============================================================

    var bulkFileList = [];
    var bulkCamera = document.getElementById("bulk-camera");
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

    // Camera: each photo adds to the queue
    bulkCamera.addEventListener("change", function () {
        if (this.files[0]) {
            addBulkFiles(this.files);
            this.value = ""; // reset so they can take another photo right away
        }
    });

    // File picker: select multiple existing photos
    bulkFilesInput.addEventListener("change", function () {
        addBulkFiles(this.files);
    });

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
        addBulkFiles(e.dataTransfer.files);
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
        bulkSubmit.textContent = "";
        bulkSubmit.innerHTML = '<span class="btn-icon">&#128270;</span> Identify All (' + bulkFileList.length + ')';

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
                bulkProgressText.textContent = "Identifying LEGO pieces...";
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
    //  HELPERS
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
            var shortCategory = p.category.split(" / ")[0];
            html += '<span class="badge badge-category">' + escapeHtml(shortCategory) + '</span>';
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
