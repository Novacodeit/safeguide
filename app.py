from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
import requests
import os
from dotenv import load_dotenv
from twilio.rest import Client as TwilioClient

load_dotenv()
app = Flask(__name__)
CORS(app)

# ── PROMPTS ────────────────────────────────────────────────────────────────

GUIDANCE_PROMPT = """You are SafeGuide, a calm AI emergency companion.
You MUST respond entirely in the language specified by the user. This is critical.
Give exactly 4 numbered safety steps. Each step under 15 words. No preamble.
After step 4, on a new line write the closing message also in the same language.

Format:
1. [action]
2. [action]
3. [action]
4. [action]
[closing message in same language as steps]"""

RECOVERY_PROMPT = """You are SafeGuide helping someone after an emergency has passed.
Give exactly 4 numbered recovery steps for what to do now.
Focus on: checking safety, reporting damage, contacting aid, next actions.
Each step must be under 15 words. No preamble.

Format:
1. [action]
2. [action]
3. [action]
4. [action]"""

LANG_NAMES = {'en': 'English', 'es': 'Spanish', 'fr': 'French', 'zh': 'Chinese'}

# ── ROUTES ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/guidance', methods=['POST'])
def get_guidance():
    try:
        data       = request.json
        disaster   = data.get('disaster', 'Earthquake')
        language   = data.get('language', 'en')
        is_drill   = data.get('isDrill', False)
        lang_note  = f"Respond in {LANG_NAMES.get(language, 'English')}." if language != 'en' else ""
        drill_note = "This is a practice drill, not a real emergency." if is_drill else ""
        if language != 'en':
           lang_instruction = f"Respond ONLY in {LANG_NAMES.get(language, 'English')}."
        else:
           lang_instruction = ""

        prompt = f"Disaster: {disaster}. {drill_note} {lang_instruction}".strip()
        
        print("=== DEBUG ===")
        print("language:", language)
        print("Prompt:", prompt)
        client  = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=GUIDANCE_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        print("Claude Response:")
        print(message.content[0].text)
        print("=== END DEBUG ===")
        return jsonify({'text': message.content[0].text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/recovery', methods=['POST'])
def get_recovery():
    try:
        data      = request.json
        disaster  = data.get('disaster', 'Earthquake')
        language  = data.get('language', 'en')
        lang_note = f"Respond in {LANG_NAMES.get(language, 'English')}." if language != 'en' else ""
        prompt    = f"Post-disaster recovery for: {disaster}. {lang_note}".strip()

        client  = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=RECOVERY_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        return jsonify({'text': message.content[0].text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/alert-parents', methods=['POST'])
def alert_parents():
    try:
        data         = request.json
        to_number    = data.get('parentPhone', '').strip()
        disaster     = data.get('disaster', 'Emergency')
        student_name = data.get('studentName', 'Your child').strip() or 'Your child'
        is_drill     = data.get('isDrill', False)

        if not to_number:
            return jsonify({'error': 'No parent phone number provided'}), 400

        drill_tag = '[DRILL] ' if is_drill else ''
        body = (
            f"🚨 {drill_tag}SafeGuide Alert\n\n"
            f"{student_name} has reported a {disaster} emergency.\n"
            f"AI guidance has been activated to help them stay safe.\n\n"
            f"Please check on them immediately.\n\n"
            f"— SafeGuide AI Emergency Companion"
        )

        twilio = TwilioClient(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )
        twilio.messages.create(
            body=body,
            from_=os.getenv('TWILIO_PHONE_NUMBER'),
            to=to_number
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts')
def get_alerts():
    alerts = []

    # USGS — real-time earthquakes magnitude 2.5+ in past hour
    try:
        res = requests.get(
            'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_hour.geojson',
            timeout=5
        )
        for f in res.json()['features'][:3]:
            p = f['properties']
            alerts.append({
                'type': 'earthquake', 'icon': '🌍', 'color': '#F59E0B',
                'title': f"M{p['mag']:.1f} — {p['place']}",
                'severity': 'High' if p['mag'] >= 6 else 'Moderate' if p['mag'] >= 4 else 'Low'
            })
    except:
        pass

    # NOAA NWS — tornadoes, hurricanes, tsunamis, wildfires
    try:
        res = requests.get(
            'https://api.weather.gov/alerts/active?status=actual&message_type=alert&urgency=Immediate,Expected',
            timeout=5,
            headers={'User-Agent': 'SafeGuide/1.0 (school-emergency-companion)'}
        )
        icon_map = {
            'tornado':   ('🌪️', '#818CF8'),
            'hurricane': ('🌀', '#A78BFA'),
            'tsunami':   ('🌊', '#38BDF8'),
            'wildfire':  ('🔥', '#EF4444'),
            'fire':      ('🔥', '#EF4444'),
        }
        for f in res.json().get('features', [])[:5]:
            ev = f['properties']['event'].lower()
            for k, (icon, color) in icon_map.items():
                if k in ev:
                    alerts.append({
                        'type': k, 'icon': icon, 'color': color,
                        'title': f['properties'].get('headline') or f['properties']['event'],
                        'severity': f['properties'].get('severity', 'Unknown')
                    })
                    break
    except:
        pass

    return jsonify(alerts[:4])


if __name__ == '__main__':
    print('\n🚨 SafeGuide is running!')
    print('   Open http://localhost:5000 in your browser\n')
    app.run(debug=True, port=5000)