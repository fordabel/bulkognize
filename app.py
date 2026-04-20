"""
Bulkognize - LEGO Minifig Identification Web App
Wraps the Brickognize API for use at Bricks & Minifigs stores.
Run with: python app.py
"""

import os
import io
import csv
import time
import uuid
import json
import base64
import tempfile
from datetime import datetime

import re

import cv2
import numpy as np
import requests
from flask import (
    Flask, render_template, request, jsonify, send_file, session
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bulkognize-" + uuid.uuid4().hex)

BRICKOGNIZE_URL = "https://api.brickognize.com/predict/"
BULK_DELAY = 0.3  # seconds between API calls in bulk mode

# Store bulk results in a temp directory keyed by session
RESULTS_DIR = os.path.join(tempfile.gettempdir(), "bulkognize_results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def call_brickognize(image_bytes, filename="image.jpg"):
    """Send an image to the Brickognize API and return parsed results."""
    files = {"query_image": (filename, image_bytes, "image/jpeg")}
    try:
        resp = requests.post(BRICKOGNIZE_URL, files=files, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        results = []
        for item in items:
            bricklink_url = ""
            for site in item.get("external_sites", []):
                if site.get("name", "").lower() == "bricklink":
                    bricklink_url = site.get("url", "")
                    break
            results.append({
                "id": item.get("id", ""),
                "name": item.get("name", "Unknown"),
                "score": round(item.get("score", 0) * 100, 1),
                "img_url": item.get("img_url", ""),
                "category": item.get("category", ""),
                "type": item.get("type", ""),
                "bricklink_url": bricklink_url,
            })
        return results
    except requests.exceptions.Timeout:
        return {"error": "The identification service took too long. Please try again."}
    except requests.exceptions.ConnectionError:
        return {"error": "Could not reach the identification service. Check your internet connection."}
    except Exception as e:
        return {"error": f"Something went wrong: {str(e)}"}


@app.route("/")
def index():
    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex
    return render_template("index.html")


@app.route("/api/predict", methods=["POST"])
def predict():
    """Single image prediction."""
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No image selected"}), 400

    image_bytes = file.read()
    results = call_brickognize(image_bytes, file.filename)

    if isinstance(results, dict) and "error" in results:
        return jsonify(results), 502

    # Encode the uploaded image as base64 for display
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")

    return jsonify({
        "uploaded_image": f"data:image/jpeg;base64,{img_b64}",
        "predictions": results,
    })


@app.route("/api/bulk", methods=["POST"])
def bulk_predict():
    """Multiple image prediction with delay between calls."""
    files = request.files.getlist("images")
    if not files or (len(files) == 1 and files[0].filename == ""):
        return jsonify({"error": "No images provided"}), 400

    all_results = []
    errors = []

    for i, file in enumerate(files):
        if file.filename == "":
            continue

        image_bytes = file.read()
        results = call_brickognize(image_bytes, file.filename)

        if isinstance(results, dict) and "error" in results:
            errors.append({"filename": file.filename, "error": results["error"]})
        else:
            img_b64 = base64.b64encode(image_bytes).decode("utf-8")
            all_results.append({
                "filename": file.filename,
                "uploaded_image": f"data:image/jpeg;base64,{img_b64}",
                "predictions": results,
            })

        # Respect the API: wait between calls (skip delay after last image)
        if i < len(files) - 1:
            time.sleep(BULK_DELAY)

    # Save results for CSV download
    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex
    results_path = os.path.join(RESULTS_DIR, f"{session['session_id']}.json")
    with open(results_path, "w") as f:
        json.dump(all_results, f)

    return jsonify({
        "results": all_results,
        "errors": errors,
        "total": len(all_results),
    })


def detect_and_crop(image_bytes):
    """Find distinct foreground objects in an image and return them as JPEG bytes.

    Designed for photos of multiple minifigs/pieces on a plain-ish background.
    Uses Otsu thresholding + contour finding. Auto-flips polarity based on
    corner brightness so it works for both light and dark backgrounds.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)

    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # If corners (likely background) are bright, invert so foreground = white.
    corner_mean = float(np.mean([
        blurred[0, 0], blurred[0, -1],
        blurred[-1, 0], blurred[-1, -1],
    ]))
    if corner_mean > 127:
        binary = cv2.bitwise_not(binary)

    # Clean up small specks and fill small holes inside figures.
    kernel = np.ones((7, 7), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    total_area = h * w
    min_area = total_area * 0.004  # skip tiny specks (< 0.4% of image)
    max_area = total_area * 0.6    # skip giant blobs that are probably the background

    boxes = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw * bh < min_area or bw * bh > max_area:
            continue
        boxes.append((x, y, bw, bh))

    # Sort roughly top-to-bottom, then left-to-right (rows bucketed by ~10% of image height).
    row_bucket = max(1, h // 10)
    boxes.sort(key=lambda b: (b[1] // row_bucket, b[0]))

    crops = []
    pad = max(10, min(h, w) // 80)
    for x, y, bw, bh in boxes:
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(w, x + bw + pad)
        y2 = min(h, y + bh + pad)
        crop = img[y1:y2, x1:x2]
        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if ok:
            crops.append(buf.tobytes())

    return crops


@app.route("/api/multi", methods=["POST"])
def multi_predict():
    """One photo with multiple figures/pieces: detect each, identify each."""
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No image selected"}), 400

    image_bytes = file.read()
    crops = detect_and_crop(image_bytes)

    if not crops:
        return jsonify({
            "error": "Couldn't find distinct figures in that photo. "
                     "Try a clearer photo on a plain background with the figures separated."
        }), 400

    all_results = []
    errors = []
    base_name = os.path.splitext(file.filename)[0] or "photo"

    for i, crop_bytes in enumerate(crops):
        crop_name = f"{base_name}_fig{i + 1}.jpg"
        results = call_brickognize(crop_bytes, crop_name)

        if isinstance(results, dict) and "error" in results:
            errors.append({"filename": crop_name, "error": results["error"]})
        else:
            img_b64 = base64.b64encode(crop_bytes).decode("utf-8")
            all_results.append({
                "filename": crop_name,
                "uploaded_image": f"data:image/jpeg;base64,{img_b64}",
                "predictions": results,
            })

        if i < len(crops) - 1:
            time.sleep(BULK_DELAY)

    # Save under the same session key so the existing CSV download works.
    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex
    results_path = os.path.join(RESULTS_DIR, f"{session['session_id']}.json")
    with open(results_path, "w") as f:
        json.dump(all_results, f)

    return jsonify({
        "results": all_results,
        "errors": errors,
        "total": len(all_results),
        "detected": len(crops),
    })


TYPE_MAP = {
    "minifig": "M", "fig": "M",
    "part": "P",
    "set": "S",
    "gear": "G",
    "book": "B",
    "catalog": "C",
}


def fetch_bricklink_prices(item_id, item_type_raw):
    """Scrape BrickLink price guide for an item. Returns dict with price fields."""
    empty = {
        "last6_new_avg": "", "last6_used_avg": "",
        "current_new_avg": "", "current_used_avg": "",
    }
    if not item_id:
        return empty
    type_code = TYPE_MAP.get(item_type_raw.lower(), "M") if item_type_raw else "M"
    url = f"https://www.bricklink.com/catalogPG.asp?{type_code}={item_id}&ColorID=0"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # BrickLink price guide has a 4-column summary table:
        #   Last 6 Months Sales: New | Used
        #   Current Items for Sale: New | Used
        # Each column has: Times Sold/Total Lots, Total Qty, Min, Avg, Qty Avg, Max.
        # We want "Avg Price" (not "Qty Avg Price") from each of the 4 columns, in order.
        # Negative lookbehind excludes the "Qty Avg Price" rows.
        avg_pattern = re.compile(
            r'(?<!Qty )Avg Price:.*?<B>US&nbsp;\$([\d,.]+)</B>', re.DOTALL
        )
        matches = avg_pattern.findall(html)

        keys = ["last6_new_avg", "last6_used_avg", "current_new_avg", "current_used_avg"]
        prices = {keys[i]: matches[i] for i in range(min(len(matches), 4))}

        return {k: prices.get(k, "") for k in empty}

    except Exception:
        return empty


@app.route("/api/bulk/csv")
def bulk_csv():
    """Download last bulk results as CSV with BrickLink pricing."""
    sid = session.get("session_id", "")
    results_path = os.path.join(RESULTS_DIR, f"{sid}.json")

    if not os.path.exists(results_path):
        return jsonify({"error": "No bulk results found. Run a bulk scan first."}), 404

    with open(results_path, "r") as f:
        all_results = json.load(f)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Source Image", "Prediction Rank", "Confidence %",
        "Item ID", "Name",
        "BL Last 6 Mo Avg (New)", "BL Last 6 Mo Avg (Used)",
        "BL Current For Sale Avg (New)", "BL Current For Sale Avg (Used)",
        "BrickLink URL",
    ])

    for result in all_results:
        filename = result.get("filename", "")
        for rank, pred in enumerate(result.get("predictions", []), 1):
            item_id = pred.get("id", "")
            item_type = pred.get("type", "")
            prices = fetch_bricklink_prices(item_id, item_type)

            writer.writerow([
                filename,
                rank,
                pred.get("score", ""),
                item_id,
                pred.get("name", ""),
                prices["last6_new_avg"],
                prices["last6_used_avg"],
                prices["current_new_avg"],
                prices["current_used_avg"],
                pred.get("bricklink_url", ""),
            ])
            # Small delay to be respectful to BrickLink
            time.sleep(0.5)

    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"bulkognize_results_{timestamp}.csv",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"\n  Bulkognize is running!")
    print(f"  Open http://localhost:{port} in your browser\n")
    app.run(debug=True, host="0.0.0.0", port=port)
