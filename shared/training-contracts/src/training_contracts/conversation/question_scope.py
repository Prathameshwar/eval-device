"""Conservative English scope selection, never a question/answer lookup table."""

import json
import re

PERSONAL = frozenset(
    "i me my mine we us our ours he him his she her hers they them their "
    "it this that these those yesterday today tomorrow last recently recent "
    "usual usually normally current currently tried took before after "
    "name age height weight job work school family hobbies hobby pets pet "
    "occupation cook cooks sleep sleeps eat eats ate drink drinks live lives "
    "like likes enjoy enjoys feel feels travel travels commute commutes "
    "favorite favourite prefer preference preferences breakfast weekend "
    "symptom symptoms pain chest fever cough coughing faint fainted "
    "medicine medicines medication medications treatment treatments antibiotic antibiotics "
    "pill pills allergy allergies diagnosis diagnose disease diabetes "
    "ignore instruction instructions prompt system scenario patient case".split()
)
PROCEDURE = re.compile(
    r"^how (?:do you|can one|does one|to) (?:make|prepare|boil|wash|clean|fold|plant|build|write)\b"
)
GENERAL = re.compile(
    r"^(?:what (?:is|are)\b|what does .+\bmean[?.!]*$|why (?:does|do|is|are|can)\b|"
    r"how (?:does|do|is|are)\b|who (?:wrote|invented|discovered|painted|composed)\b|"
    r"where (?:is|are)\b|when (?:was|were)\b)"
)
GENERAL_QUANTITY = re.compile(r"^how (?:many|much|long)\s+[a-z0-9]")
GENERAL_EXPLANATION = re.compile(r"^(?:can|could) you explain\s+[a-z0-9]")
WEATHER = re.compile(
    r"^why (?:does|is|can) it (?:rain|raining|snow|snowing|hail|hailing|drizzle|drizzling|thunder|thundering)\b"
)
GREETING = re.compile(
    r"^(?:hello|hi|hey|good morning|good afternoon|good evening)[!. ,]*(?:how are you[?!.]*)?$"
)
BARE_REFERENCE = re.compile(
    r"^(?:what about|could you explain|can you explain|explain|and) (?:it|this|that)[?!.]*$"
)
CLINICAL = frozenset(
    "symptom symptoms pain painful chest fever cough coughing faint fainted fainting "
    "medicine medicines medication medications treatment treatments antibiotic antibiotics "
    "pill pills allergy allergies diagnosis diagnoses diagnose disease diseases diabetes "
    "blood pressure pulse temperature oxygen heart lungs breathing breathless palpitation palpitations "
    "injury wound wounds illness health sick nausea vomiting dizzy dizziness ears ringing "
    "smoke smoking alcohol drug drugs surgery surgeries history condition conditions "
    "hurt hurts ache aches discomfort cancer insulin headache headaches".split()
)
LIFESTYLE = frozenset(
    "name age old occupation job work workday school teach teaching commute commuting education educational qualification qualifications degree "
    "meal meals food breakfast cook cooking eat eats ate drink water tea coffee "
    "sleep slept sleeping hours morning evening family live lives home "
    "hobby hobbies relax relaxation exercise exercises pets pet weekend weekends "
    "travel travelled traveled travel worried worry mood coming".split()
)
BACKGROUND_SUBJECTS = {
    "food_drink": frozenset(
        "meal meals food breakfast cook cooks cooking eat eats ate drink drinks water tea coffee".split()
    ),
    "sleep_activity": frozenset("sleep slept sleeping hours morning exercise exercises".split()),
    "work_home": frozenset(
        "occupation job work workday school teach teaching commute commuting education educational qualification qualifications degree morning evening family live lives home relax relaxation".split()
    ),
    "personality": frozenset(
        "hobby hobbies relax relaxation worried worry mood emotion emotions feelings anxious nervous scared".split()
    ),
    "additional": frozenset(
        "exercise exercises pets pet weekend weekends travel travelled traveled coming".split()
    ),
}
REFERENCES = frozenset(
    "it this that these those i me my mine we us our he him his she her hers they them their "
    "said told mention mentioned earlier same similar help helps better worse change changed changes "
    "cause caused causes affect affects trigger triggers relieve relieves "
    "ignore instruction instructions prompt system scenario patient case".split()
)

MEASUREMENT_SUBJECTS = {
    "pulse": {"vitals.pulse_bpm"},
    "heart rate": {"vitals.heart_rate_bpm"},
    "blood pressure": {"vitals.systolic_mmhg", "vitals.diastolic_mmhg"},
    "temperature": {"vitals.temperature_c"},
    "oxygen saturation": {"vitals.spo2_percent"},
    "breathing rate": {"vitals.respirations_per_minute"},
    "pain score": {"vitals.pain_0_10"},
    "height": {"patient.height_cm"},
    "weight": {"patient.weight_kg"},
    "age": {"patient.age_years"},
}
MEASUREMENT_QUERY = re.compile(
    r"^(?:what is|what's|tell me) your (pulse|heart rate|blood pressure|temperature|oxygen saturation|"
    r"breathing rate|pain score|height|weight|age)[?!.]*$"
)
MEASUREMENT_ALTERNATIVES = {
    "how tall are you": "height",
    "how old are you": "age",
    "how fast are you breathing": "breathing rate",
    "what degree of pain are you experiencing": "pain score",
    "how would you rate your pain": "pain score",
    "what is your pain level": "pain score",
}
QUALIFICATION_QUERY = re.compile(
    r"^(?:tell me about|what is|what's|what are) your (?:educational )?"
    r"(?:qualification|qualifications|education|degree)[?!.]*$"
)
SOCIAL_QUERIES = (
    (
        re.compile(r"^(?:do you smoke|are you a smoker)[?!.]*$"),
        r"\b(?:smok\w*|nonsmok\w*|cigarettes?|tobacco)\b",
    ),
    (
        re.compile(r"^(?:how much alcohol do you drink|do you drink alcohol)[?!.]*$"),
        r"\b(?:alcohol|drink\w*)\b",
    ),
)
CURRENT_SYMPTOMS = re.compile(
    r"^(?:are there|do you have|are you having) (?:any )?other symptoms"
    r"(?: (?:with|along with) (?:the |your )?([a-z ]+))?[?!.]*$"
)
INTAKE_QUERY = re.compile(
    r"\b(?:what (?:brings|brought) you (?:in|here)|why (?:are you here|have you come)|"
    r"reason for (?:this|your) visit)\b"
)


def measurement_subjects(question):
    """Only a complete, unqualified patient measurement question can shed other facts."""
    text = " ".join(question.casefold().split())
    match = MEASUREMENT_QUERY.fullmatch(text)
    measurement = match[1] if match else MEASUREMENT_ALTERNATIVES.get(text.rstrip("?!."))
    return MEASUREMENT_SUBJECTS.get(measurement, set()) if measurement else set()


def clinical_terms(document, language):
    if language != "en":
        return []

    def text(value):
        if isinstance(value, dict):
            if isinstance(value.get(language), str):
                yield value[language]
            else:
                for item in value.values():
                    yield from text(item)
        elif isinstance(value, list):
            for item in value:
                yield from text(item)

    history = {key: value for key, value in (document.get("history") or {}).items() if key != "social"}
    words = set(re.findall(r"[a-z]+", " ".join(text([document.get("presentation"), history])).casefold()))
    common = set(
        "about after before began during each from have little minutes most normal only otherwise rest started that their them there these they this until usually very when where which while with days hours".split()
    )
    return sorted(word for word in words if len(word) > 3 and word not in common)


def family_medical_question(question):
    words = set(re.findall(r"[a-z]+", question.casefold()))
    return bool(words & {"family", "relatives", "relative"}) and bool(
        words & (CLINICAL | {"problem", "problems", "asthma", "wheeze", "wheezing"})
    )


def education_question(question):
    words = set(re.findall(r"[a-z]+", question.casefold()))
    return bool(words & {"education", "educational", "qualification", "qualifications"}) or (
        "degree" in words and not words & CLINICAL
    )


def presentation_question(question, sources, intake_sources):
    """Only an explicit current presentation can shed history and other domains."""
    text = " ".join(question.casefold().split()).rstrip("?!. ")
    presentation = {key: fact for key, fact in sources.items() if key in intake_sources}
    if not presentation:
        return False
    if text in {"how are you feeling", "how are you feeling today", "how are you feeling right now"}:
        return True
    match = re.fullmatch(
        r"(?:what makes your ([a-z -]{1,60}) (?:worse|better)|"
        r"what (?:triggers|worsens|aggravates) your ([a-z -]{1,60}))",
        text,
    )
    if not match:
        return False
    words = set(re.findall(r"[a-z]+", match[1] or match[2])) - {"the"}
    symptoms = {
        "pain",
        "chest",
        "cough",
        "wheeze",
        "wheezing",
        "breathing",
        "asthma",
        "tightness",
        "palpitations",
    }
    recorded = {
        word for fact in presentation.values() for word in re.findall(r"[a-z]+", fact["text"].casefold())
    }
    return bool(words & symptoms) and all(
        any(word == known or len(word) >= 4 and known.startswith(word[:4]) for known in recorded)
        for word in words
    )


def standalone_lifestyle(question, context):
    if context.get("language") != "en" or not isinstance(question, str) or not question.isascii():
        return False
    words = set(re.findall(r"[a-z]+", question.casefold()))
    if family_medical_question(question):
        return False
    if len(question) > 8000 or question.count("?") > 1 or INTAKE_QUERY.search(question.casefold()):
        return False
    return bool(words & LIFESTYLE) and not words.intersection(
        CLINICAL | REFERENCES | set(context.get("clinical_terms", []))
    )


def lifestyle_prompt(context, question):
    """Select authored areas, never synthesize facts or run a separate routing model."""
    system = context["lifestyle_system"]
    if context.get("reply_format") == "fact-selection-v1":
        from .sources import constrained_sources, selection_prompt

        words = set(re.findall(r"[a-z]+", question.casefold()))
        areas = {area for area, subjects in BACKGROUND_SUBJECTS.items() if subjects.intersection(words)}
        if words.intersection({"cook", "cooks", "cooking"}) and not words.intersection(
            {"work", "family", "live"}
        ):
            areas.discard("work_home")
        if words.intersection({"commute", "commuting", "work"}):
            areas.discard("additional")
        if words.intersection(
            {"name", "age", "old", "occupation", "job", "work", "school", "teach", "teaching"}
        ):
            areas.add("identity")
        if words.intersection({"family", "live", "lives"}):
            areas.add("social")
        sources = {key: value for key, value in context["fact_sources"].items() if value.get("area") in areas}
        # A specific hobby/pet/preference can be authored in any of the five background areas.
        if words.intersection(
            {
                "hobby",
                "hobbies",
                "pet",
                "pets",
                "prefer",
                "preference",
                "water",
                "weekend",
                "weekends",
                "travelled",
                "traveled",
            }
        ):
            sources = {
                key: value
                for key, value in context["fact_sources"].items()
                if value.get("area") in BACKGROUND_SUBJECTS
            }
        sources, missing = constrained_sources(sources, question)
        return selection_prompt(sources, missing, "standalone_lifestyle")
    if "\nDATA:\n" not in system:
        return system  # Older snapshots keep their frozen prompt.
    prefix, data = system.split("\nDATA:\n", 1)
    data, suffix = data.split("\nEND DATA.", 1)
    life = json.loads(data)
    words = set(re.findall(r"[a-z]+", question.casefold()))
    areas = {area for area, subjects in BACKGROUND_SUBJECTS.items() if subjects.intersection(words)}
    # A cooking question's 'home' does not make the household schedule relevant.
    if words.intersection({"cook", "cooks", "cooking"}) and not words.intersection(
        {"work", "family", "live"}
    ):
        areas.discard("work_home")
    selected = {"background": [fact for fact in life.get("background", []) if fact.get("id") in areas]}
    if words.intersection({"name", "age", "old", "occupation", "job", "work", "school", "teach", "teaching"}):
        selected["identity"] = life.get("identity", [])
    if words.intersection({"family", "live", "lives"}):
        selected["social"] = life.get("social", [])
    return prefix + "\nDATA:\n" + json.dumps(selected, ensure_ascii=False) + "\nEND DATA." + suffix


def prompt_mode(context, messages):
    if not messages:
        return "grounded_patient"
    content = messages[0].get("content", "")
    for key, mode in (
        ("general_system", "standalone_general"),
        ("greeting_system", "standalone_greeting"),
        ("clarification_system", "standalone_clarification"),
    ):
        if context.get(key) and content == context[key]:
            return mode
    life = context.get("lifestyle_system")
    if context.get("reply_format") == "fact-selection-v1":
        if content.startswith("Prompt scope: patient_measurement."):
            return "patient_measurement"
        return (
            "standalone_lifestyle"
            if content.startswith("Prompt scope: standalone_lifestyle.")
            else "grounded_patient"
        )
    delimiter = "\nDATA:\n"
    if (
        life
        and content.split(delimiter, 1)[0] == life.split(delimiter, 1)[0]
        and content != context.get("system")
    ):
        return "standalone_lifestyle"
    return "grounded_patient"


def standalone_general(question, language, clinical_vocabulary=()):
    if language != "en" or not isinstance(question, str) or not question.isascii():
        return False
    text = " ".join(question.casefold().split())
    if not text or len(text) > 8000 or text.count("?") > 1:
        return False
    if GREETING.fullmatch(text):
        return True
    words = set(re.findall(r"[a-z]+", text))
    clinical = CLINICAL | set(clinical_vocabulary)
    blocked = words & PERSONAL
    subject = words - {"what", "is", "are", "does", "mean", "a", "an", "the"}
    if (
        subject
        and subject.issubset(clinical)
        and (
            text.startswith(("what is ", "what are "))
            or (text.startswith("what does ") and text.rstrip("?!. ").endswith("mean"))
        )
    ):
        blocked -= clinical  # An unqualified definition is knowledge, not a patient claim.
    elif words.intersection(clinical_vocabulary) and not GENERAL_EXPLANATION.match(text):
        return False  # A case-specific symptom/location follow-up cannot shed its facts.
    if blocked == {"it"} and WEATHER.match(text):
        blocked.clear()  # Weather uses an impersonal 'it', not a dialogue referent.
    if blocked:
        return False
    procedure = bool(PROCEDURE.match(text))
    explanation = bool(GENERAL_EXPLANATION.match(text))
    # 'You/your' can mean the generic reader only for an unqualified procedure.
    if words & {"your", "yours"} and not procedure:
        return False
    if "you" in words and not (procedure or explanation):
        return False
    quantity = bool(GENERAL_QUANTITY.match(text)) and bool(
        words
        - {
            "how",
            "many",
            "much",
            "long",
            "is",
            "are",
            "was",
            "were",
            "do",
            "does",
            "there",
            "a",
            "an",
            "the",
            "in",
            "of",
            "to",
            "for",
        }
    )
    return procedure or explanation or quantity or bool(GENERAL.match(text))


def select_messages(context, messages):
    """Old snapshots retain their original prompt; only clear new subjects shed history."""
    general = context.get("general_system")
    name_words = set(re.findall(r"[a-z]+", str(context.get("patient_name", "")).casefold()))
    question_words = (
        set(re.findall(r"[a-z]+", str(messages[-1].get("content", "")).casefold())) if messages else set()
    )
    if (
        context.get("reply_format") == "fact-selection-v1"
        and context.get("language") == "en"
        and len(messages) >= 2
    ):
        from .sources import selection_prompt

        question = " ".join(messages[-1].get("content", "").casefold().split())
        for query, evidence in SOCIAL_QUERIES:
            if messages[-1].get("role") == "user" and query.fullmatch(question):
                sources = {
                    key: fact
                    for key, fact in context["fact_sources"].items()
                    if fact.get("area") == "social" and re.search(evidence, fact["text"], re.I)
                }
                return [{**messages[0], "content": selection_prompt(sources)}, dict(messages[-1])]
    if (
        context.get("reply_format") == "fact-selection-v1"
        and context.get("language") == "en"
        and len(messages) >= 2
        and messages[-1].get("role") == "user"
        and (subjects := measurement_subjects(messages[-1].get("content", "")))
    ):
        from .sources import selection_prompt

        sources = {
            key: fact
            for key, fact in context["fact_sources"].items()
            if subjects.intersection(fact["subject"].split("; "))
        }
        available = {subject for fact in sources.values() for subject in fact["subject"].split("; ")}
        return [
            {
                **messages[0],
                "content": selection_prompt(sources, not subjects.issubset(available), "patient_measurement"),
            },
            dict(messages[-1]),
        ]
    if (
        context.get("language") == "en"
        and context.get("clarification_system")
        and len(messages) == 2
        and BARE_REFERENCE.fullmatch(" ".join(messages[-1].get("content", "").casefold().split()))
    ):
        return [{**messages[0], "content": context["clarification_system"]}, dict(messages[-1])]
    if (
        context.get("reply_format") == "fact-selection-v1"
        and context.get("language") == "en"
        and len(messages) >= 2
        and messages[-1].get("role") == "user"
        and QUALIFICATION_QUERY.fullmatch(" ".join(messages[-1]["content"].casefold().split()))
    ):
        from .sources import constrained_sources, selection_prompt

        sources, missing = constrained_sources(context["fact_sources"], messages[-1]["content"])
        return [{**messages[0], "content": selection_prompt(sources, missing)}, dict(messages[-1])]
    if (
        general
        and not name_words.intersection(question_words)
        and len(messages) >= 2
        and messages[-1].get("role") == "user"
        and standalone_general(
            messages[-1].get("content"), context.get("language"), context.get("clinical_terms", [])
        )
    ):
        system = (
            context.get("greeting_system", general)
            if GREETING.fullmatch(" ".join(messages[-1]["content"].casefold().split()))
            else general
        )
        return [{**messages[0], "content": system}, dict(messages[-1])]
    if (
        context.get("lifestyle_system")
        and len(messages) >= 2
        and messages[-1].get("role") == "user"
        and standalone_lifestyle(messages[-1].get("content"), context)
    ):
        return [
            {**messages[0], "content": lifestyle_prompt(context, messages[-1]["content"])},
            dict(messages[-1]),
        ]
    if (
        context.get("reply_format") == "fact-selection-v1"
        and len(messages) >= 4
        and messages[-1].get("role") == "user"
        and re.fullmatch(r"(?:and )?how often[?!.]*", " ".join(messages[-1]["content"].casefold().split()))
        and messages[-3].get("role") == "user"
        and messages[-2].get("role") == "assistant"
        and standalone_lifestyle(messages[-3]["content"], context)
    ):
        from .sources import selection_prompt

        previous = lifestyle_prompt(context, messages[-3]["content"])
        sources = json.loads(previous.split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
        spoken = messages[-2]["content"]
        selected = {key: fact for key, fact in sources.items() if fact["text"] in spoken}
        if selected and any(
            re.search(
                r"\b(?:most days|every|each|daily|weekly|monthly|(?:once|twice|times) (?:a|per))\b",
                fact["text"],
                re.I,
            )
            for fact in selected.values()
        ):
            # Dialogue identifies the antecedent; only its existing frozen facts provide evidence.
            return [
                {**messages[0], "content": selection_prompt(selected, scope="standalone_lifestyle")},
                *[dict(message) for message in messages[-3:]],
            ]
    # An explicit clinical subject cannot be grounded by earlier unrelated life/general replies.
    # Pronoun-only follow-ups keep all recent pairs, including their original antecedent.
    if context.get("reply_format") == "fact-selection-v1" and question_words.intersection(CLINICAL):
        clinical_messages = [messages[0]]
        for index in range(1, len(messages) - 1, 2):
            previous = messages[index].get("content", "")
            if not standalone_general(
                previous, context.get("language"), context.get("clinical_terms", [])
            ) and not standalone_lifestyle(previous, context):
                clinical_messages.extend(messages[index : index + 2])
        messages = [*clinical_messages, messages[-1]]
    if context.get("reply_format") == "fact-selection-v1" and messages:
        from .sources import constrained_sources, selection_prompt

        sources = context["fact_sources"]
        if context.get("intake_sources") and re.match(
            r"^what (?:has )?(?:brings|brought) you (?:in|here)\b", messages[-1]["content"].casefold().strip()
        ):
            sources = {key: fact for key, fact in sources.items() if key in context["intake_sources"]}
        symptom_query = CURRENT_SYMPTOMS.fullmatch(" ".join(messages[-1]["content"].casefold().split()))
        if context.get("intake_sources") and symptom_query:
            presentation = {key: fact for key, fact in sources.items() if key in context["intake_sources"]}
            words = {
                word
                for fact in presentation.values()
                for word in re.findall(r"[a-z]+", fact["text"].casefold())
            }
            if set(re.findall(r"[a-z]+", symptom_query[1] or "")).issubset(words):
                sources = presentation
        if question_words.intersection(CLINICAL):
            areas = {
                area
                for area, subjects in BACKGROUND_SUBJECTS.items()
                if subjects.intersection(question_words)
            }
            sources = {
                key: fact
                for key, fact in sources.items()
                if fact.get("area") not in BACKGROUND_SUBJECTS or fact.get("area") in areas
            }
        intake_sources = context.get("intake_sources", [])
        current_presentation = presentation_question(messages[-1]["content"], sources, intake_sources)
        sources, missing = constrained_sources(
            sources, messages[-1]["content"], intake_sources=intake_sources
        )
        if current_presentation:
            return [{**messages[0], "content": selection_prompt(sources, missing)}, dict(messages[-1])]
        return [{**messages[0], "content": selection_prompt(sources, missing)}, *messages[1:]]
    return list(messages)
