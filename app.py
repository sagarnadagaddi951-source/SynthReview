from flask import Flask, render_template, request, jsonify
from transformers import T5ForConditionalGeneration, T5Tokenizer
import requests
import re
import os

app = Flask(__name__)

# --- API KEY HIDDEN FROM USER ---
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "91450373f9msh35af52807147cc7p1743b6jsn2e56927852de")

# --- LOAD T5 MODEL ONCE AT STARTUP ---
print("Loading T5 model...")
tokenizer = T5Tokenizer.from_pretrained("t5-small")
model = T5ForConditionalGeneration.from_pretrained("t5-small")
print("Model ready.")

def extract_asin(url):
    match = re.search(r"/dp/([A-Z0-9]{10})", url)
    if match:
        return match.group(1)
    match = re.search(r"/gp/product/([A-Z0-9]{10})", url)
    if match:
        return match.group(1)
    # If user directly pastes ASIN
    if re.match(r"^[A-Z0-9]{10}$", url.strip()):
        return url.strip()
    return None

def fetch_balanced_reviews(asin):
    all_reviews = []
    for star in ["5_STARS", "3_STARS", "1_STAR"]:
        url = "https://real-time-amazon-data.p.rapidapi.com/product-reviews"
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"
        }
        params = {
            "asin": asin,
            "country": "IN",
            "page": "1",
            "star_rating": star,
            "sort_by": "TOP_REVIEWS"
        }
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            if "data" in data and "reviews" in data["data"]:
                all_reviews.extend(data["data"]["reviews"])
        except Exception as e:
            print(f"Error fetching {star}: {e}")
    return all_reviews

def get_product_info(asin):
    url = "https://real-time-amazon-data.p.rapidapi.com/product-details"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"
    }
    params = {"asin": asin, "country": "IN"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()
        if "data" in data:
            return {
                "title": data["data"].get("product_title", "Product"),
                "rating": data["data"].get("product_star_rating", "N/A"),
                "image": data["data"].get("product_photo", "")
            }
    except:
        pass
    return {"title": "Product", "rating": "N/A", "image": ""}

def summarize_reviews(reviews):
    combined = " ".join([
        r.get("review_comment", "")
        for r in reviews
        if r.get("review_comment", "").strip()
    ])
    if not combined.strip():
        return "No review content available to summarize."
    input_text = "summarize: " + combined
    tokens = tokenizer.encode(
        input_text,
        return_tensors="pt",
        max_length=512,
        truncation=True
    )
    output = model.generate(
        tokens,
        max_length=150,
        min_length=40,
        length_penalty=2.0,
        num_beams=4
    )
    return tokenizer.decode(output[0], skip_special_tokens=True)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/summarize", methods=["POST"])
def summarize():
    data = request.get_json()
    url_input = data.get("url", "").strip()

    if not url_input:
        return jsonify({"error": "Please enter an Amazon product URL."}), 400

    asin = extract_asin(url_input)
    if not asin:
        return jsonify({"error": "Could not find a valid product ID in the URL. Please check and try again."}), 400

    # Fetch product info
    product = get_product_info(asin)

    # Fetch reviews
    reviews = fetch_balanced_reviews(asin)
    if not reviews:
        return jsonify({"error": "No reviews found for this product."}), 404

    # Summarize
    summary = summarize_reviews(reviews)

    return jsonify({
        "title": product["title"],
        "rating": product["rating"],
        "image": product["image"],
        "summary": summary
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
