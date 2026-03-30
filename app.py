import os
import json
import datetime
import io
import base64
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from groq import Groq
from PIL import Image

load_dotenv()

app = Flask(__name__)
DATA_FILE = 'user_data.json'

# Load keys from .env
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

# Model IDs
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
TEXT_MODEL = "llama-3.3-70b-versatile"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "quests_completed": 0,
            "current_streak": 0,
            "protection_left": 0,
            "last_check_in": str(datetime.date.today() - datetime.timedelta(days=1)),
            "current_goal": "Complete a 30-minute workout"
        }
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
        if "current_goal" not in data:
            data["current_goal"] = "Complete a 30-minute workout"
        return data

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def generate_new_goal():
    try:
        prompt_messages = [
            {
                "role": "system", 
                "content": "You are a creative quest generator. Respond ONLY with a 5-10 word photo challenge. Do not use quotes, introductions, or explanations."
            },
            {
                "role": "user", 
                "content": "Generate one unique daily photo quest. Do not use 'bird', 'puddle', or 'street sign'."
            }
        ]
        
        # Use the variable TEXT_MODEL defined at the top of your script
        completion = client.chat.completions.create(
            model=TEXT_MODEL, 
            messages=prompt_messages,
            temperature=0.7, 
            max_completion_tokens=40, # Increased slightly to prevent cutoff
            top_p=0.9
        )
        
        # Extract and clean
        raw_content = completion.choices[0].message.content
        if not raw_content:
            raise ValueError("Empty response from model")

        new_goal = raw_content.strip().replace('"', '').replace("'", "")
        
        # Final validation to ensure we didn't get a blank string
        return new_goal if len(new_goal) > 3 else "Find a unique architectural detail"

    except Exception as e:
        # This will now print the actual error to your console for easier debugging
        print(f"Goal Generation Error: {type(e).__name__} - {e}")
        return "Take a picture of something green"

def run_passive_maintenance(data):
    today = datetime.date.today()
    last_date = datetime.date.fromisoformat(data['last_check_in'])
    days_missed = (today - last_date).days - 1 

    if days_missed > 0:
        for _ in range(days_missed):
            if data['protection_left'] > 0:
                data['protection_left'] -= 1
            else:
                data['current_streak'] = 0
        data['last_check_in'] = str(today - datetime.timedelta(days=1))
    return data

def encode_image(image_bytes):
    return base64.b64encode(image_bytes).decode('utf-8')

@app.route('/')
def index():
    data = load_data()
    data = run_passive_maintenance(data)
    save_data(data)
    return render_template('index.html', data=data)

@app.route('/upload', methods=['POST'])
def upload():
    data = load_data()
    data = run_passive_maintenance(data)
    
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"})
    
    image_file = request.files['image']
    
    try:
        img = Image.open(image_file).convert('RGB')
        img.thumbnail((1024, 1024))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=80)
        base64_image = encode_image(img_byte_arr.getvalue())
        
        current_goal = data.get("current_goal", "Complete a 30-minute workout")
        
        prompt = (
            f"Analyze this image carefully. The user's goal is: '{current_goal}'. "
            "Describe any text or activity you see related to this goal, then "
            "conclude with the word 'VERIFIED' if the goal is met, or 'FAILED' if it is not."
        )
        
        completion = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            temperature=0.2, 
            max_completion_tokens=150
        )
        
        response_text = completion.choices[0].message.content
        print(f"AI Reasoning: {response_text}")
        
        is_valid = "VERIFIED" in response_text.upper()
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Vision Error: {str(e)}"})

    if is_valid:
        today_str = str(datetime.date.today())
        data['quests_completed'] += 1
        
        if data['last_check_in'] == today_str:
            data['protection_left'] += 1
        else:
            data['current_streak'] += 1
            data['last_check_in'] = today_str
        
        # Generate new goal using the fixed GPT OSS 120B call
        data['current_goal'] = generate_new_goal()
            
        save_data(data)
        return jsonify({"status": "success", "message": f"Verified! New Goal: {data['current_goal']}"})
    
    return jsonify({"status": "fail", "message": "Verification failed. Try a clearer photo."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)