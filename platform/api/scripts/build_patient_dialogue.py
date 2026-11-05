"""Author the everyday-question dialogue expansion for migration 0014.

Source of truth for the added topics and non-clinical replies. Re-run after editing the
tables below; it rewrites `migrations/versions/0014_patient_case_templates.json` and fails
if any case stops validating, outgrows the document budget or outgrows the routing prompt.

    uv run python scripts/build_patient_dialogue.py

The content is fictional practice material and still requires educator review.
"""

import json
from pathlib import Path

from training_contracts import canonical
from training_contracts.scenarios import PublishedScenarioV2

from pms_api.modules.patient_context import patient_context

VERSIONS = Path(__file__).parents[1] / "migrations/versions"

# Spoken replies for utterances that request no case fact. command_ack acknowledges without
# claiming the body moved: manikin physical capability is not modelled yet.
REPLIES = {
    "clarification": {
        "en": "I am sorry, doctor, I do not know about that. You can ask me about my problem, "
        "my history or how I have been feeling.",
        "hi": "माफ़ कीजिए डॉक्टर, मुझे इसके बारे में पता नहीं है। आप मेरी तकलीफ़, मेरी पिछली "
        "जानकारी या मेरी हालत के बारे में पूछ सकते हैं।",
    },
    "backchannel": {"en": "Yes, doctor, I am listening.", "hi": "जी डॉक्टर, मैं सुन रहा हूँ।"},
    "command_ack": {
        "en": "I will try to do that, doctor. Please tell me exactly how you would like me to move.",
        "hi": "मैं ऐसा करने की कोशिश करूँगा डॉक्टर। कृपया बताइए कि आप मुझे कैसे हिलाना चाहते हैं।",
    },
    "boundary": {
        "en": "I would rather not answer that, doctor. Please ask me about my health.",
        "hi": "मैं इसका जवाब नहीं देना चाहता डॉक्टर। कृपया मेरी सेहत के बारे में पूछिए।",
    },
}

# Trigger wording lives in `intent`: it is the only topic text the routing prompt carries.
WIDER_INTENT = {
    "social_history": "Smoking, tobacco, alcohol, drinking, lifestyle and home background",
    "associated": "Other symptoms that came with the main problem, and relevant absent symptoms",
    "past_history": "Previous illnesses, diagnoses and long-standing conditions",
    "medications": "Current medicines, tablets, inhalers, syrups, doses and treatment taken so far",
}

# Everyday interview questions the clinical topic set did not cover.
EVERYDAY = [
    {
        "id": "diet_meals",
        "intent": "Diet, meals, what and when the patient ate, yesterday's food, cooking, salt, fasting",
        "examples": ["What did you eat yesterday?", "आप क्या खाते हैं?"],
        "answer": {
            "en": "I eat home-cooked meals three times a day, mostly rice, dal and vegetables. "
            "Yesterday I ate the same as usual.",
            "hi": "मैं दिन में तीन बार घर का बना खाना खाता हूँ, ज़्यादातर चावल, दाल और सब्ज़ी। "
            "कल भी मैंने रोज़ जैसा ही खाना खाया।",
        },
    },
    {
        "id": "sleep",
        "intent": "Sleep, bedtime, hours slept, waking at night, rest and tiredness on waking",
        "examples": ["When did you sleep last night?", "आपकी नींद कैसी है?"],
        "answer": {
            "en": "I usually sleep about seven hours, from around eleven at night until six in the morning.",
            "hi": "मैं आम तौर पर सात घंटे सोता हूँ, रात ग्यारह बजे से सुबह छह बजे तक।",
        },
    },
    {
        "id": "appetite_weight",
        "intent": "Appetite, eating less than usual, weight gain or weight loss",
        "examples": ["How is your appetite?", "क्या आपका वज़न कम हुआ है?"],
        "answer": {
            "en": "My appetite is normal and my weight has not changed.",
            "hi": "मेरी भूख ठीक है और मेरा वज़न नहीं बदला है।",
        },
    },
    {
        "id": "daily_routine",
        "intent": "A typical day, daily routine, working hours, journey to work, rest during the day",
        "examples": ["Tell me about your usual day.", "आपका दिन कैसा बीतता है?"],
        "answer": {
            "en": "I leave for school at eight in the morning, teach until four, and spend the evening "
            "at home with my family.",
            "hi": "मैं सुबह आठ बजे स्कूल के लिए निकलता हूँ, चार बजे तक पढ़ाता हूँ, और शाम घर पर "
            "अपने परिवार के साथ बिताता हूँ।",
        },
    },
    {
        "id": "exercise",
        "intent": "Exercise, physical activity, walking, sport and how active the patient is",
        "examples": ["Do you exercise?", "क्या आप कसरत करते हैं?"],
        "answer": {
            "en": "I walk to the market most days. I do not do any other regular exercise.",
            "hi": "मैं अक्सर बाज़ार तक पैदल जाता हूँ। इसके अलावा मैं कोई नियमित कसरत नहीं करता।",
        },
    },
    {
        "id": "mood_stress",
        "intent": "Mood, worry, stress, tension, anxiety, low feeling and what the patient is worried about",
        "examples": ["Are you worried about anything?", "क्या आपको कोई तनाव है?"],
        "answer": {
            "en": "I feel a little worried about this problem, but otherwise my mood is normal.",
            "hi": "मुझे इस तकलीफ़ की थोड़ी चिंता है, बाकी मेरा मन ठीक रहता है।",
        },
    },
    {
        "id": "bowel_bladder",
        "intent": "Bowels, stool, constipation, loose motion, passing urine and how often",
        "examples": ["Any change in your bowels?", "पेशाब में कोई दिक्कत है?"],
        "answer": {
            "en": "My bowels are regular and passing urine is normal for me.",
            "hi": "मेरा पेट नियमित रूप से साफ़ होता है और पेशाब सामान्य रहता है।",
        },
    },
    {
        "id": "home_situation",
        "intent": "Home, who the patient lives with, family at home, housing and support when unwell",
        "examples": ["Who is at home with you?", "आप घर पर किसके साथ रहते हैं?"],
        "answer": {
            "en": "I live with my family in a rented flat. They help me when I am unwell.",
            "hi": "मैं अपने परिवार के साथ किराए के फ़्लैट में रहता हूँ। बीमार होने पर वे मेरी मदद करते हैं।",
        },
    },
    {
        "id": "travel_contact",
        "intent": "Recent travel, journeys away from home, and contact with anyone who was unwell",
        "examples": ["Have you travelled recently?", "क्या आप कहीं बाहर गए थे?"],
        "answer": {
            "en": "I have not travelled anywhere recently.",
            "hi": "मैं हाल में कहीं बाहर नहीं गया हूँ।",
        },
    },
    {
        "id": "vaccination",
        "intent": "Vaccination and immunisation history, including tetanus, influenza and COVID vaccines",
        "examples": ["Are your vaccinations up to date?", "आपके टीके लगे हैं?"],
        "answer": {
            "en": "I had my childhood vaccinations. I do not remember having any vaccine in the last few years.",
            "hi": "मुझे बचपन के टीके लगे थे। पिछले कुछ सालों में कोई टीका लगवाने की मुझे याद नहीं है।",
        },
    },
]

# Where the presenting complaint must change an everyday answer, so the two cannot contradict.
OVERRIDES = {
    "alex_dry_cough": {
        "sleep": {
            "en": "I sleep about seven hours, but the cough wakes me a few times most nights.",
            "hi": "मैं सात घंटे सोता हूँ, लेकिन खाँसी की वजह से रात में कई बार नींद टूट जाती है।",
        }
    },
    "alex_fever_cough": {
        "sleep": {
            "en": "The fever and sweating have broken my sleep for the last three nights.",
            "hi": "पिछली तीन रातों से बुख़ार और पसीने की वजह से मेरी नींद टूट रही है।",
        },
        "appetite_weight": {
            "en": "I have not felt like eating since the fever began. My weight has not changed.",
            "hi": "बुख़ार शुरू होने के बाद से मेरा खाने का मन नहीं करता। मेरा वज़न नहीं बदला है।",
        },
        "travel_contact": {
            "en": "I have not travelled recently, but a colleague at school had a similar cough last week.",
            "hi": "मैं हाल में कहीं बाहर नहीं गया, लेकिन पिछले हफ़्ते स्कूल में एक साथी को ऐसी ही खाँसी थी।",
        },
    },
    "alex_painful_urination": {
        "bowel_bladder": {
            "en": "My bowels are regular. Passing urine burns and I go more often, as I told you.",
            "hi": "मेरा पेट नियमित रूप से साफ़ होता है। जैसा मैंने बताया, पेशाब में जलन होती है और मुझे बार-बार जाना पड़ता है।",
        }
    },
    "alex_flank_pain": {
        "bowel_bladder": {
            "en": "My bowels are regular. I noticed pink urine once, as I mentioned.",
            "hi": "मेरा पेट नियमित रूप से साफ़ होता है। जैसा मैंने बताया, एक बार पेशाब गुलाबी दिखा था।",
        }
    },
    "alex_blood_pressure": {
        "diet_meals": {
            "en": "I eat home-cooked meals three times a day. I was told to use less salt, but I often forget.",
            "hi": "मैं दिन में तीन बार घर का बना खाना खाता हूँ। मुझे नमक कम करने को कहा गया था, "
            "लेकिन मैं अक्सर भूल जाता हूँ।",
        }
    },
    "alex_kidney_followup": {
        "diet_meals": {
            "en": "I eat home-cooked meals three times a day. I was advised to reduce salt and I drink "
            "about two litres of water daily.",
            "hi": "मैं दिन में तीन बार घर का बना खाना खाता हूँ। मुझे नमक कम करने की सलाह दी गई थी और "
            "मैं रोज़ लगभग दो लीटर पानी पीता हूँ।",
        }
    },
}


def expanded(document):
    dialogue = document["dialogue"]
    for name, text in REPLIES.items():
        dialogue[name] = dict(text)
    for topic in dialogue["topics"]:
        if topic["id"] in WIDER_INTENT:
            topic["intent"] = WIDER_INTENT[topic["id"]]
    overrides = OVERRIDES.get(document["code"], {})
    existing = {topic["id"] for topic in dialogue["topics"]}
    for topic in EVERYDAY:
        assert topic["id"] not in existing, f"{document['code']} already defines {topic['id']}"
        added = json.loads(json.dumps(topic))
        if topic["id"] in overrides:
            added["answer"] = dict(overrides[topic["id"]])
        added["disclosure"] = "on_question"
        dialogue["topics"].append(added)
    return document


def main():
    rows = json.loads((VERSIONS / "0013_patient_case_templates.json").read_text(encoding="utf-8"))
    report = []
    built = []
    for row in rows:
        document = expanded(json.loads(json.dumps(row["document"])))
        PublishedScenarioV2.model_validate(document)
        size = len(canonical(document).encode("utf-8"))
        assert size <= 48000, f"{row['code']} document is {size} bytes"
        topics = document["dialogue"]["topics"]
        assert len(topics) <= 32, f"{row['code']} has {len(topics)} topics"
        prompt = patient_context(document, "en", "hello")["system"]
        report.append((row["code"], len(topics), size, len(prompt.encode("utf-8"))))
        built.append({"code": row["code"], "document": document})
    path = VERSIONS / "0014_patient_case_templates.json"
    path.write_text(json.dumps(built, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{'case':26} {'topics':>6} {'document B':>11} {'routing B':>10}")
    for code, topics, size, prompt in report:
        print(f"{code:26} {topics:6} {size:11} {prompt:10}")
    print("wrote", path.name)


if __name__ == "__main__":
    main()
