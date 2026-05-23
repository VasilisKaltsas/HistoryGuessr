import json
import logging
import os
import random
import re

import anthropic
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("histo_guessr")

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
loaded_dotenv = load_dotenv(dotenv_path)
logger.info("Loaded .env: %s (%s)", dotenv_path, loaded_dotenv)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
logger.info("ANTHROPIC_API_KEY present: %s", bool(ANTHROPIC_API_KEY))
if not ANTHROPIC_API_KEY:
    raise RuntimeError("Missing ANTHROPIC_API_KEY in environment or .env file")

app = FastAPI(title="HistoGuessr Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="."), name="static")

MODEL_NAME = "claude-sonnet-4-5"
CLIENT = anthropic.Anthropic()

CONTINENTS = [
    "Africa",
    "Asia",
    "Europe",
    "North America",
    "South America",
    "Oceania",
    "Antarctica",
]
TIME_PERIODS = [
    "Ancient Bronze Age",
    "Classical Antiquity",
    "Late Antiquity",
    "Medieval era",
    "Renaissance",
    "Early Modern period",
    "Industrial Revolution",
    "Age of Exploration",
    "Post-colonial 20th century",
    "Modern era",
]
EVENT_TYPES = [
    "a battle or military campaign",
    "a major migration or exploration",
    "a cultural or religious ceremony",
    "a trade expedition or caravan journey",
    "a scientific or astronomical discovery",
    "a political rebellion or revolution",
    "a landmark construction or architectural achievement",
    "a courtly ritual or festival",
    "a natural disaster response",
    "an artistic or intellectual breakthrough",
]

SYSTEM_PROMPT_EN = (
    "You are a historical event generator for a geography/history game. "
    "Generate immersive, mysterious historical scenarios spanning 3000 BC to 2026 AD from all continents. "
    "Mix specific events (50%) with historical periods, civilizations, and eras (50%). "
    "Examples: Vikings in Scandinavia ~1050 AD, Byzantine Empire, Silk Road trade routes, Ming Dynasty, Aztec civilization, Roman Republic, etc. "
    "Never reveal location names or dates in the description. Write EXACTLY 3 sentences maximum with only visual and sensory clues. "
    "Focus on what the player sees, hears, feels. Every word must be a meaningful hint. No filler. "
    "Also include a separate factual 2-3 sentence summary of the event in English, using real names, dates, locations, and outcomes. "
    "Also generate exactly 3 progressive hints in English to help struggling players: "
    "Hint 1 (very subtle): only an environmental or sensory detail — climate, terrain, vegetation, sounds, smells. No cultural references whatsoever. "
    "Hint 2 (moderate): one cultural, architectural, or material detail that narrows it down without naming the civilization or location. "
    "Hint 3 (more direct): narrows down the region or era significantly but does NOT name the location or exact date. "
    "Always return event_name_en as the English event name in the JSON output, regardless of the selected language. "
    "Make sure the year, description, and returned lat/lng are all consistent with the same scene. "
    "Return only valid JSON with no extra text, no markdown, no backticks."
)

USER_PROMPT_EN = (
    "Generate one immersive historical scenario in exactly 3 sentences or fewer. Use only sensory/visual clues. "
    "Also include a separate factual 2-3 sentence historical summary in English. Use specific factual names, dates, places, and outcomes, not vague descriptions. "
    "Always include event_name_en as the English event name in the JSON output. "
    "Return only valid JSON with no extra text, no markdown, no backticks. "
    "The returned lat/lng must be geographically consistent with the scene and the selected era. "
    "Return JSON exactly in this format: "
    "{\"description\": \"...(max 3 sentences)...\", \"lat\": ..., \"lng\": ..., \"year\": ..., "
    "\"bc\": false, \"event_name\": \"...\", \"event_name_en\": \"...\", \"summary\": \"...(factual 2-3 sentence historical summary in English)...\", "
    "\"hints\": [\"subtle environmental hint\", \"moderate cultural hint\", \"more direct region/era hint\"]}"
)

SYSTEM_PROMPT_EL = (
    "Είσαι ένας δημιουργός ιστορικών σεναρίων για ένα παιχνίδι γεωγραφίας και ιστορίας. "
    "Δημιούργησε μυστηριακά ιστορικά σενάρια από το 3000 π.Χ. έως το 2026 μ.Χ. από όλες τις ηπείρους. "
    "Ανάμειξε συγκεκριμένα γεγονότα (50%) με ιστορικές περιόδους, πολιτισμούς και εποχές (50%). "
    "Παραδείγματα: Βίκινγκς στη Σκανδιναβία ~1050 μ.Χ., Βυζαντινή Αυτοκρατορία, Μεταξένιος Δρόμος, Δυναστεία Μινγ, Ατζτέκοι, Ρωμαϊκή Δημοκρατία κ.λπ. "
    "Μην αποκαλύπτεις ονόματα τοποθεσιών ή ημερομηνίες στην περιγραφή. Γράψε ΑΚΡΙΒΩΣ 3 προτάσεις με αισθητηριακές και οπτικές ενδείξεις. "
    "Εστίασε στο τι βλέπει, ακούει, νιώθει ο παίκτης. Κάθε λέξη πρέπει να είναι ένα σημαντικό κλειδί. Καμία γεμάτα. "
    "Επίσης περιέλαβε μια ξεχωριστή, ακριβή περίληψη 2-3 προτάσεων στα ελληνικά για το ιστορικό γεγονός, με πραγματικά ονόματα, ημερομηνίες, τόπους και αποτελέσματα. "
    "Δημιούργησε επίσης ακριβώς 3 προοδευτικές υποδείξεις στα ελληνικά για να βοηθήσεις τον παίκτη: "
    "Υπόδειξη 1 (πολύ λεπτή): μόνο περιβαλλοντική ή αισθητηριακή λεπτομέρεια — κλίμα, τοπίο, βλάστηση, ήχοι, οσμές. Καμία πολιτισμική αναφορά. "
    "Υπόδειξη 2 (μέτρια): μία πολιτισμική, αρχιτεκτονική ή υλική λεπτομέρεια που στενεύει την αναζήτηση χωρίς να ονομάζει τον πολιτισμό ή τοποθεσία. "
    "Υπόδειξη 3 (πιο άμεση): στενεύει σημαντικά την περιοχή ή την εποχή αλλά ΔΕΝ αποκαλύπτει την τοποθεσία ή την ακριβή ημερομηνία. "
    "Πρέπει να επιστρέψεις το event_name_en στα Αγγλικά στο JSON output, ανεξάρτητα από την επιλεγμένη γλώσσα. "
    "Βεβαιώσου ότι το έτος, η περιγραφή και τα επιστρεφόμενα lat/lng είναι συμβατά με το ίδιο σκηνικό. "
    "Επιστρέψτε μόνο έγκυρο JSON χωρίς επιπλέον κείμενο, χωρίς markdown, χωρίς backticks."
)

USER_PROMPT_EL = (
    "Δημιούργησε ένα μυστηριακό ιστορικό σενάριο σε ακριβώς 3 προτάσεις ή λιγότερες. Χρησιμοποίησε μόνο αισθητηριακές/οπτικές ενδείξεις. "
    "Συμπεριλάβετε μια ξεχωριστή, ακριβή περίληψη 2-3 προτάσεων στα ελληνικά. Χρησιμοποίησε συγκεκριμένα πραγματικά ονόματα, ημερομηνίες, τόπους και αποτελέσματα, όχι αόριστες περιγραφές. "
    "Πρέπει επίσης να επιστρέψεις το event_name_en στα Αγγλικά στο JSON, ανεξαρτήτως της επιλεγμένης γλώσσας. "
    "Επιστρέψτε μόνο έγκυρο JSON χωρίς επιπλέον κείμενο, χωρίς markdown, χωρίς backticks. "
    "Επιστροφή JSON ακριβώς σε αυτή τη μορφή: "
    "{\"description\": \"...(μέχρι 3 προτάσεις)...\", \"lat\": ..., \"lng\": ..., \"year\": ..., "
    "\"bc\": false, \"event_name\": \"...\", \"event_name_en\": \"...\", \"summary\": \"...(ακριβής περίληψη 2-3 προτάσεων στα ελληνικά)...\", "
    "\"hints\": [\"λεπτή περιβαλλοντική υπόδειξη\", \"μέτρια πολιτισμική υπόδειξη\", \"πιο άμεση υπόδειξη περιοχής/εποχής\"]}"
)


DIFFICULTY_PROMPTS = {
    "easy": (
        "DIFFICULTY: Easy — for beginners. The description must be immediately obvious to anyone with school-level history. "
        "You MUST directly state the continent or region by name AND the approximate century or era "
        "(e.g. 'You are in ancient Egypt along the Nile', 'You stand in medieval Europe near a Gothic cathedral', "
        "'This is feudal Japan in the 12th century', 'You are in World War II-era Europe'). "
        "Include at least one famous or well-known landmark, cultural element, or historical figure associated with the place and era. "
        "A player should identify the correct area within 30 seconds."
    ),
    "medium": (
        "DIFFICULTY: Medium. Give clear but indirect cultural clues — describe specific architecture, clothing styles, "
        "tools, food, religious rituals, trade goods, vegetation, and climate — enough to narrow it down to a specific "
        "region and century. Do NOT name the civilization, empire, region, continent, or era directly. "
        "A player with moderate history knowledge should identify it in 1-2 minutes of reasoning."
    ),
    "hard": (
        "DIFFICULTY: Hard — maximum ambiguity. Write only abstract, poetic sensory impressions: smells, sounds, "
        "textures, quality of light, emotional atmosphere, temperature, wind. "
        "Absolutely NO cultural names, no architectural style names (not even 'Gothic' or 'Roman'), "
        "no recognizable crops or animals, no clothing descriptions, no time period indicators of any kind. "
        "Even a professional historian should need to think carefully. The scene must feel hauntingly ambiguous."
    ),
}

STYLE_PROMPTS = {
    "story": (
        "STYLE: Story mode. Write the description as immersive 2nd-person narrative prose, as if the player "
        "is physically present at the scene. Use vivid, flowing sensory language."
    ),
    "clues": (
        "STYLE: Clues mode. Write the description as exactly 4-5 short bullet point clues. "
        "Each bullet starts with '•' on its own line separated by \\n. Each bullet is one direct observational "
        "hint about what is visible, heard, or felt — under 15 words each. "
        "Example: '• Massive stone columns rise from a white marble floor\\n• Men in white tunics argue in the shade'"
    ),
}

USER_PROMPT_EN_CLUES = (
    "Generate one historical scenario as exactly 4-5 bullet point clues (•), one per line. "
    "Also include a separate factual 2-3 sentence historical summary in English with specific names, dates, places, and outcomes. "
    "Always include event_name_en as the English event name in the JSON. "
    "Return only valid JSON with no extra text, no markdown, no backticks. "
    "The returned lat/lng must be geographically consistent with the scene and era. "
    "Return JSON exactly: "
    "{\"description\": \"• clue one\\n• clue two\\n• clue three\\n• clue four\\n• clue five\", "
    "\"lat\": ..., \"lng\": ..., \"year\": ..., \"bc\": false, \"event_name\": \"...\", "
    "\"event_name_en\": \"...\", \"summary\": \"...(factual summary)...\", "
    "\"hints\": [\"subtle environmental hint\", \"moderate cultural hint\", \"more direct region/era hint\"]}"
)

USER_PROMPT_EL_CLUES = (
    "Δημιούργησε ένα ιστορικό σενάριο ως ακριβώς 4-5 σύντομες ενδείξεις bullet (•), μία ανά γραμμή. "
    "Συμπεριέλαβε ξεχωριστή ακριβή περίληψη 2-3 προτάσεων στα ελληνικά με πραγματικά ονόματα, ημερομηνίες, τόπους. "
    "Επίστρεψε το event_name_en πάντα στα Αγγλικά. "
    "Επίστρεψε μόνο έγκυρο JSON χωρίς markdown. "
    "Επιστροφή JSON ακριβώς: "
    "{\"description\": \"• ένδειξη ένα\\n• ένδειξη δύο\\n• ένδειξη τρία\\n• ένδειξη τέσσερα\\n• ένδειξη πέντε\", "
    "\"lat\": ..., \"lng\": ..., \"year\": ..., \"bc\": false, \"event_name\": \"...\", "
    "\"event_name_en\": \"...\", \"summary\": \"...(ακριβής περίληψη)...\", "
    "\"hints\": [\"λεπτή περιβαλλοντική υπόδειξη\", \"μέτρια πολιτισμική υπόδειξη\", \"πιο άμεση υπόδειξη περιοχής/εποχής\"]}"
)


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace == -1 or last_brace == -1 or last_brace < first_brace:
        raise ValueError("No JSON object found in Claude response")

    payload = text[first_brace:last_brace + 1].strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse JSON from Claude response: {exc}. "
            f"Payload extracted: {payload[:400]}"
        ) from exc


@app.get("/")
async def root():
    return FileResponse("index.html")


@app.post("/generate-event")
async def generate_event(request: Request, language: str = "en"):
    language = language.lower() if language else "en"
    if language not in ("en", "el"):
        language = "en"

    try:
        body = await request.json()
    except Exception:
        body = {}

    difficulty = body.get("difficulty", "medium")
    style = body.get("style", "story")
    if difficulty not in DIFFICULTY_PROMPTS:
        difficulty = "medium"
    if style not in STYLE_PROMPTS:
        style = "story"

    system_prompt = SYSTEM_PROMPT_EL if language == "el" else SYSTEM_PROMPT_EN
    if style == "clues":
        user_prompt = USER_PROMPT_EL_CLUES if language == "el" else USER_PROMPT_EN_CLUES
    else:
        user_prompt = USER_PROMPT_EL if language == "el" else USER_PROMPT_EN

    # Build a language-aware style prompt so Greek sessions never produce
    # English bullet points regardless of style mode.
    style_prompt = STYLE_PROMPTS[style]
    if language == "el":
        style_prompt += (
            " IMPORTANT: Write ALL description content (including every bullet point) "
            "in Greek (Ελληνικά). Do not use English words in the description field."
        )

    seed_continent = random.choice(CONTINENTS)
    seed_time_period = random.choice(TIME_PERIODS)
    seed_event_type = random.choice(EVENT_TYPES)
    prompt_seed = (
        f"Use this creative seed for the event: continent={seed_continent}, "
        f"time period={seed_time_period}, event type={seed_event_type}. "
        "The description, year, and returned coordinates must all match the same scene and be consistent with that chosen setting. "
        "Choose a unique historical moment or period that fits the selected continent and era, and do not repeat the same place or theme twice in a row."
    )
    payload_text = (
        f"{system_prompt}\n\n"
        f"{DIFFICULTY_PROMPTS[difficulty]}\n\n"
        f"{style_prompt}\n\n"
        f"{prompt_seed}\n\n"
        f"{user_prompt}"
    )
    payload_messages = [{"role": "user", "content": payload_text}]

    logger.info("Sending to Claude — difficulty=%s style=%s language=%s", difficulty, style, language)
    try:
        response = CLIENT.messages.create(
            model=MODEL_NAME,
            messages=payload_messages,
            max_tokens=2048,
            temperature=0.8,
            stop_sequences=["\nHuman:", "\nAssistant:"],
        )
    except Exception as exc:
        logger.exception("Claude API request failed with Anthropic SDK error")
        raise HTTPException(status_code=502, detail="Claude API request failed") from exc

    text = None
    if hasattr(response, "content"):
        content = getattr(response, "content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                text = first.get("text")
            else:
                text = getattr(first, "text", None)
        elif isinstance(content, str):
            text = content

    if not text and isinstance(response, dict):
        text = response.get("completion") or response.get("content")

    if not text:
        logger.error("Claude API returned empty completion payload: %s", response)
        raise HTTPException(status_code=502, detail="Claude API returned empty completion")

    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    logger.info("Raw Claude response (first 800 chars): %s", text[:800])

    try:
        event = extract_json(text)
    except ValueError as exc:
        logger.exception("Failed to parse event JSON from Claude response. Raw text: %s", text[:600])
        raise HTTPException(status_code=502, detail=str(exc))

    required_keys = {"description", "lat", "lng", "year", "bc", "event_name", "event_name_en", "summary"}
    missing = required_keys - event.keys()
    if missing:
        logger.error("Claude response missing required keys: %s. Full event: %s", missing, event)
        raise HTTPException(status_code=502, detail=f"Claude response JSON missing required keys: {missing}")

    # hints are optional — fall back to empty list so the game still works
    if "hints" not in event or not isinstance(event["hints"], list):
        logger.warning("Claude response missing hints field — using empty list")
        event["hints"] = []

    return JSONResponse(content=event)


@app.get("/wiki-image")
async def wiki_image(query: str):
    user_agent = "HistoGuessr/1.0 (https://example.com)"
    image_url = None
    title = None

    try:
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.requote_uri(query)}"
        logger.info("Fetching Wikipedia summary image URL: %s", summary_url)
        response = requests.get(summary_url, timeout=20, headers={"User-Agent": user_agent})
        if response.status_code == 200:
            data = response.json()
            title = data.get("title")
            image_url = data.get("thumbnail", {}).get("source")
            if image_url:
                logger.info("Wikipedia summary response for %s: title=%s image=%s", query, title, image_url)
                return JSONResponse(content={"image": image_url, "title": title})

        pageimages_url = "https://en.wikipedia.org/w/api.php"
        pageimages_params = {
            "action": "query",
            "format": "json",
            "titles": query,
            "prop": "pageimages",
            "pithumbsize": 500,
            "redirects": 1,
        }
        response = requests.get(pageimages_url, params=pageimages_params, timeout=20, headers={"User-Agent": user_agent})
        if response.status_code == 200:
            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                title = title or page.get("title")
                image_url = page.get("thumbnail", {}).get("source")
                if image_url:
                    logger.info("Wikipedia pageimages response for %s: title=%s image=%s", query, title, image_url)
                    return JSONResponse(content={"image": image_url, "title": title})

        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srlimit": 1,
        }
        response = requests.get(search_url, params=search_params, timeout=20, headers={"User-Agent": user_agent})
        if response.status_code == 200:
            search_data = response.json()
            search_results = search_data.get("query", {}).get("search", [])
            if search_results:
                first_title = search_results[0].get("title")
                if first_title:
                    title = title or first_title
                    pageimages_params = {
                        "action": "query",
                        "format": "json",
                        "titles": first_title,
                        "prop": "pageimages",
                        "pithumbsize": 500,
                        "redirects": 1,
                    }
                    response = requests.get(search_url, params=pageimages_params, timeout=20, headers={"User-Agent": user_agent})
                    if response.status_code == 200:
                        data = response.json()
                        pages = data.get("query", {}).get("pages", {})
                        for page in pages.values():
                            image_url = page.get("thumbnail", {}).get("source")
                            if image_url:
                                logger.info("Wikipedia search fallback image for %s: title=%s image=%s", query, title, image_url)
                                return JSONResponse(content={"image": image_url, "title": title})

        logger.warning("No Wikipedia image found for query: %s", query)
        return JSONResponse(content={"image": None, "title": title})
    except Exception as exc:
        logger.exception("Error fetching Wikipedia image for %s", query)
        return JSONResponse(content={"image": None, "title": None})
