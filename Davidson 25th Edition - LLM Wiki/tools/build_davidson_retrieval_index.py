#!/usr/bin/env python3
"""Build a portable, source-first retrieval index for Davidson 25.

This keeps the proven LLM-Wiki retrieval shape without a claims index:

* ``concept_index.json`` groups medical terms and aliases;
* ``occurrence_index.json`` maps each term occurrence to source passages,
  visuals, tables, and the explicit Part/Chapter/section path;
* ``term_lookup.json`` is the fast normalized-term lookup;
* ``structure_lookup.json`` is the book hierarchy and unit-to-source map;
* ``passage_index.jsonl`` is a portable paragraph source store;
* ``visual_index.json`` is a portable visual/table metadata store.

The extractor is intentionally a candidate generator. It uses source text,
headings, reconstructed table text, captions, and a conservative medical-term
lexicon. It does not silently claim that a generated term is clinically
correct, and it does not infer relationships between terms.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


STATUS = "generated_not_verified"
GENERAL_TERM_MIN_FREQUENCY = 20

CATEGORY_LABELS = {
    "conditions": "Conditions",
    "anatomy": "Anatomy",
    "symptoms_signs": "Symptoms and signs",
    "etiology_risk_factors": "Aetiology and risk factors",
    "pathophysiology": "Pathophysiology",
    "investigations": "Investigations",
    "management_treatment": "Management and treatment",
    "medications": "Medications",
    "rehabilitation": "Rehabilitation",
    "complications_prognosis": "Complications and prognosis",
    "measurements": "Measurements and clinical values",
    "definitions_abbreviations": "Definitions and abbreviations",
    "procedures": "Procedures",
    "populations": "Populations",
    "section_topics": "Section topics",
    "visuals": "Visuals and tables",
    "general_medical_terms": "General medical terms",
}

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also",
    "although", "am", "among", "an", "and", "another", "any", "are",
    "around", "as", "at", "be", "because", "been", "before", "being",
    "between", "both", "but", "by", "can", "cannot", "could", "despite",
    "did", "do", "does", "during", "each", "either", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here",
    "hers", "him", "his", "how", "if", "in", "include", "includes",
    "including", "into", "is", "it", "its", "itself", "may", "might",
    "more", "most", "much", "must", "my", "no", "not", "of", "on", "one",
    "only", "or", "other", "our", "out", "over", "per", "same", "she",
    "should", "since", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "then", "there", "these", "they", "this", "those",
    "through", "to", "too", "under", "until", "up", "upon", "us", "use",
    "used", "using", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "within",
    "without", "would", "you", "your", "than", "via", "often", "usually",
    "common", "important", "known", "new", "patient", "patients", "clinical",
    "medical", "medicine", "health", "disease", "disorders", "condition",
    "conditions", "chapter", "figure", "table", "box", "page", "pages",
    "part", "section", "first", "second", "third", "four", "five", "six",
}

GENERIC_EXCLUDE = STOPWORDS | {
    "according", "associated", "available", "based", "called", "cause", "causes",
    "certain", "change", "changes", "consider", "different", "due", "effect",
    "effects", "factor", "factors", "form", "forms", "following", "found",
    "given", "group", "groups", "however", "level", "levels", "make", "made",
    "method", "methods", "need", "number", "possible", "present", "provide",
    "provided", "result", "results", "several", "show", "shown", "similar",
    "specific", "study", "support", "treatment", "type", "types", "well",
}

MEDICAL_MARKERS = {
    "disease", "disorder", "condition",
    "amyloidosis", "anaemia", "anemia", "aneurysm", "angina", "arthritis",
    "asthma", "atrophy", "cancer", "carcinoma", "cardiomyopathy", "cirrhosis",
    "dementia", "dermatitis", "diabetes", "dystrophy", "embolism", "encephalitis",
    "epilepsy", "fibrosis", "fracture", "haemorrhage", "hemorrhage", "hepatitis",
    "hypertension", "infection", "inflammation", "injury", "insufficiency",
    "leukaemia", "leukemia", "lymphoma", "malignancy", "meningitis", "metastasis",
    "myeloma", "myopathy", "neoplasm", "nephritis", "neuropathy", "oedema", "edema",
    "oncology", "osteoporosis", "paralysis", "parkinson", "pneumonia", "psychosis",
    "seizure", "sclerosis", "stroke", "syndrome", "thrombosis", "tumour", "tumor",
    "vasculitis", "weakness", "dysplasia", "dysfunction", "failure", "deficiency",
    "dislocation", "sprain", "ulcer", "sepsis", "shock", "tachycardia", "bradycardia",
    "arrhythmia", "coagulopathy", "neuromuscular", "polyradiculoneuropathy",
    "rhabdomyolysis", "spondylitis", "spondylosis", "tendinopathy", "retinopathy",
    "glomerulonephritis", "gastroenteritis", "bronchiectasis", "bronchitis",
    "fibromyalgia", "osteomyelitis", "myelitis", "radiculopathy", "plexopathy",
    "arthropathy", "myelopathy", "encephalopathy", "carditis", "pericarditis",
    "endocarditis", "vasopathy", "pathology", "pathological", "lesion", "lesions",
}

ANATOMY_TERMS = {
    "abdomen", "abdominal", "ankle", "artery", "arteries", "atrium", "brain",
    "bronchus", "cerebellum", "cerebral", "cervical", "chest", "colon", "cortex",
    "cranial", "diaphragm", "duodenum", "femur", "hip", "kidney", "knee",
    "liver", "lung", "lymph", "marrow", "muscle", "nerve", "neuron", "oesophagus",
    "esophagus", "pancreas", "pelvis", "peripheral", "pharynx", "plexus", "rib",
    "spinal", "spine", "stomach", "tendon", "thoracic", "thyroid", "trachea",
    "ureter", "urethra", "uterus", "vascular", "vein", "ventricle", "wrist",
}

SYMPTOM_TERMS = {
    "ataxia", "breathlessness", "cough", "dizziness", "dyspnoea", "dyspnea",
    "fatigue", "fever", "headache", "incontinence", "itching", "jaundice", "pain",
    "paraesthesia", "paresthesia", "rash", "vomiting", "nausea", "weakness",
    "wasting", "weight", "diarrhoea", "diarrhea", "constipation", "spasticity",
    "tremor", "aphasia", "dysphagia", "dysarthria", "ataxia", "confusion",
}

INVESTIGATION_TERMS = {
    "biopsy", "blood", "culture", "ct", "csf", "ecg", "echo", "electrocardiogram",
    "electrophysiology", "emg", "imaging", "investigation", "mri", "radiograph",
    "scan", "screening", "serology", "serum", "test", "tests", "ultrasound",
    "urinalysis", "urine", "xray", "x-ray", "spirometry", "endoscopy", "genetic",
}

TREATMENT_TERMS = {
    "analgesia", "antibiotic", "chemotherapy", "dialysis", "exercise", "immunotherapy",
    "intervention", "management", "operation", "physiotherapy", "rehabilitation",
    "radiotherapy", "surgery", "transplant", "ventilation", "therapy", "treatment",
    "vaccination", "counselling", "counseling", "palliative", "supportive",
}

REHAB_TERMS = {
    "activities", "adl", "balance", "disability", "function", "functional", "gait",
    "mobility", "occupational", "participation", "physiotherapy", "prosthesis",
    "range", "rehabilitation", "splint", "strength", "transfer", "walking",
}

MEDICATION_SUFFIXES = (
    "mab", "nib", "vir", "pril", "sartan", "olol", "statin", "azole", "cillin",
    "cycline", "mycin", "caine", "prazole", "setron", "gliptin", "gliflozin",
    "lukast", "terol", "tide", "parin", "pam", "lam", "done", "dipine", "xaban",
)

CONDITION_SUFFIXES = (
    "itis", "osis", "emia", "aemia", "opathy", "oma", "iasis", "uria", "algia",
    "plegia", "paresis", "dystrophy", "sclerosis", "syndrome", "carcinoma",
)

TOKEN_RE = re.compile(r"[A-Za-zα-ωΑ-Ω][A-Za-z0-9α-ωΑ-Ω]*(?:[’'\-/][A-Za-z0-9α-ωΑ-Ω]+)*")
ACRONYM_RE = re.compile(r"^(?:[A-Z]{2,}[A-Z0-9-]*|[A-Z][A-Z0-9]{1,7}[0-9]+)$")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"Expected a JSON object: {path}")
    return value


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(ch for ch in text if ch.isalnum())


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def build_page_map(chapter_structure: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Map physical PDF pages to the printed book page and chapter.

    The chapter structure records the first physical PDF page and the first
    printed page for each chapter.  Page citations must use the printed book
    number; the physical PDF number is retained as an unambiguous navigation
    locator.  The mapping was checked against the embedded extraction's page
    labels before being used here.
    """
    page_map: dict[int, dict[str, Any]] = {}
    for part in chapter_structure.get("parts", []):
        for chapter in part.get("chapters", []):
            pdf_start = int(chapter["pdf_page_start"])
            pdf_end = int(chapter["pdf_page_end"])
            printed_start = int(chapter["printed_page_start"])
            for pdf_page in range(pdf_start, pdf_end + 1):
                printed_page = printed_start + pdf_page - pdf_start
                page_map[pdf_page] = {
                    "source_page_id": f"DAV25-PDF{pdf_page:04d}",
                    "pdf_page": pdf_page,
                    "page_number": printed_page,
                    "printed_page": printed_page,
                    "chapter_number": int(chapter["chapter_number"]),
                    "chapter_title": clean_text(chapter.get("title", "")),
                    "part": clean_text(part.get("title", "")),
                    "chapter_page_index": pdf_page - pdf_start + 1,
                }
    return page_map


def page_refs(page_ids: Iterable[str], page_map: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return portable, human-readable page references in source order."""
    references: list[dict[str, Any]] = []
    for page_id in unique(page_ids):
        match = re.search(r"(\d+)$", str(page_id))
        if not match:
            continue
        pdf_page = int(match.group(1))
        mapped = page_map.get(pdf_page)
        if mapped:
            references.append(dict(mapped))
        else:
            references.append({
                "source_page_id": str(page_id),
                "pdf_page": pdf_page,
                "page_number": None,
                "printed_page": None,
                "chapter_number": None,
                "chapter_title": None,
                "part": None,
                "chapter_page_index": None,
            })
    return references


def token_norm(token: str) -> str:
    return normalize(token)


def is_acronym(token: str) -> bool:
    return bool(ACRONYM_RE.match(token))


def medical_like(token: str) -> bool:
    value = token_norm(token)
    parts = [token_norm(part) for part in TOKEN_RE.findall(token)]
    return (
        value in MEDICAL_MARKERS
        or value in ANATOMY_TERMS
        or value in SYMPTOM_TERMS
        or value in INVESTIGATION_TERMS
        or value in TREATMENT_TERMS
        or value in REHAB_TERMS
        or value.endswith(MEDICATION_SUFFIXES)
        or value.endswith(CONDITION_SUFFIXES)
        or any(part in MEDICAL_MARKERS or part in ANATOMY_TERMS or part in SYMPTOM_TERMS for part in parts)
    )


def category_for(term: str, *, source_kind: str = "paragraph") -> str:
    value = token_norm(term)
    parts = [token_norm(part) for part in TOKEN_RE.findall(term)]
    if source_kind == "visual":
        return "visuals"
    if is_acronym(term) or any(ch.isdigit() for ch in term):
        return "definitions_abbreviations"
    if len(parts) > 1:
        if any(part.endswith(MEDICATION_SUFFIXES) for part in parts):
            return "medications"
        if any(part in REHAB_TERMS for part in parts):
            return "rehabilitation"
        if any(part in INVESTIGATION_TERMS for part in parts):
            return "investigations"
        if any(part in TREATMENT_TERMS for part in parts):
            return "management_treatment"
        if any(part in SYMPTOM_TERMS for part in parts):
            return "symptoms_signs"
        if any(part in MEDICAL_MARKERS or part.endswith(CONDITION_SUFFIXES) for part in parts):
            return "conditions"
    if value in REHAB_TERMS or any(word in value for word in ("rehabilitation", "physiotherapy", "occupationaltherapy")):
        return "rehabilitation"
    if value.endswith(MEDICATION_SUFFIXES):
        return "medications"
    if value in INVESTIGATION_TERMS or any(word in value for word in ("imaging", "diagnostic", "electrophysi")):
        return "investigations"
    if value in TREATMENT_TERMS or any(word in value for word in ("therapy", "treatment", "surgery", "management")):
        return "management_treatment"
    if value in SYMPTOM_TERMS:
        return "symptoms_signs"
    if value in ANATOMY_TERMS:
        return "anatomy"
    if any(word in value for word in ("cause", "risk", "aetiolog", "etiolog", "predispos")):
        return "etiology_risk_factors"
    if any(word in value for word in ("mechanism", "pathophysi", "physiolog", "inflamm")):
        return "pathophysiology"
    if any(word in value for word in ("complication", "prognos", "mortality", "survival", "recurrence", "relapse")):
        return "complications_prognosis"
    if any(word in value for word in ("measurement", "normalvalue", "reference", "score", "index", "scale")):
        return "measurements"
    if medical_like(term):
        return "conditions"
    return "general_medical_terms"


def display_form(forms: Iterable[str], fallback: str) -> str:
    values = [clean_text(value) for value in forms if clean_text(value)]
    if not values:
        return fallback
    return sorted(values, key=lambda value: (-len(value), value.casefold()))[0]


def alias_variants(term: str) -> list[str]:
    value = clean_text(term)
    variants = [value]
    replacements = (
        ("oedema", "edema"), ("edema", "oedema"),
        ("haem", "hem"), ("hem", "haem"),
        ("leukaemia", "leukemia"), ("leukemia", "leukaemia"),
        ("tumour", "tumor"), ("tumor", "tumour"),
        ("paediatric", "pediatric"), ("pediatric", "paediatric"),
        ("anaemia", "anemia"), ("anemia", "anaemia"),
        ("ischaemia", "ischemia"), ("ischemia", "ischaemia"),
    )
    for old, new in replacements:
        if old in value.casefold():
            variants.append(re.sub(old, new, value, flags=re.IGNORECASE))
    lower = value.casefold()
    if lower.endswith("ies") and len(value) > 4:
        variants.append(value[:-3] + "y")
    elif lower.endswith("s") and not lower.endswith(("ss", "sis", "is", "us")) and len(value) > 4:
        variants.append(value[:-1])
    return unique(variants)


def sentence_excerpt(text: str, term: str, limit: int = 520) -> str:
    source = clean_text(text)
    if not source:
        return ""
    lower_source = source.casefold()
    lower_term = clean_text(term).casefold()
    position = lower_source.find(lower_term)
    if position < 0:
        position = 0
    start = max(0, source.rfind(". ", 0, position) + 2)
    end_candidates = [point for point in (source.find(". ", position), source.find("; ", position)) if point >= 0]
    end = min(end_candidates) + 1 if end_candidates else len(source)
    excerpt = source[start:end].strip()
    if len(excerpt) > limit:
        excerpt = excerpt[: limit - 1].rstrip() + "…"
    return excerpt


def token_candidates(text: str, global_counts: Counter[str], source_kind: str = "paragraph") -> dict[tuple[str, str], set[str]]:
    """Return (category, normalized term) -> source forms for one source unit."""
    tokens = TOKEN_RE.findall(text)
    result: dict[tuple[str, str], set[str]] = defaultdict(set)
    normalized_tokens = [token_norm(token) for token in tokens]
    for raw, value in zip(tokens, normalized_tokens):
        if not value or len(value) < 3 or value in GENERIC_EXCLUDE:
            continue
        if global_counts[value] >= GENERAL_TERM_MIN_FREQUENCY or medical_like(raw) or is_acronym(raw) or any(ch.isdigit() for ch in raw):
            category = category_for(raw, source_kind=source_kind)
            # The retrieval index is a concept index, not a bag-of-words
            # index. Generic prose words remain searchable through the source
            # passage text; headings, medical terms, abbreviations, and
            # clinically meaningful phrases receive concept records.
            if category == "general_medical_terms":
                continue
            result[(category, value)].add(raw)

    # Preserve clinically meaningful multi-word terms such as chronic
    # obstructive pulmonary disease and acute inflammatory demyelinating
    # polyradiculoneuropathy. Stopwords cannot start or end the phrase.
    marker_indices = [index for index, raw in enumerate(tokens) if medical_like(raw)]
    for index in marker_indices:
        start = max(0, index - 5)
        # Prefer the phrase after the nearest boundary/stopword. This keeps
        # useful terms such as "heart failure" instead of indexing noisy
        # windows such as "patients with severe heart failure".
        for boundary in range(index - 1, start - 1, -1):
            if token_norm(tokens[boundary]) in GENERIC_EXCLUDE:
                start = boundary + 1
                break
        phrase_tokens = tokens[start:index + 1]
        phrase_norms = [token_norm(token) for token in phrase_tokens]
        if len(phrase_tokens) < 2 or len(phrase_tokens) > 6:
            continue
        if phrase_norms[0] in STOPWORDS or phrase_norms[-1] in STOPWORDS:
            continue
        phrase = " ".join(phrase_tokens)
        if normalize(phrase) in {normalize(token) for token in phrase_tokens}:
            continue
        category = category_for(phrase, source_kind=source_kind)
        result[(category, normalize(phrase))].add(phrase)
    return result


def all_texts(extraction: dict[str, Any], visual_manifest: dict[str, Any], tables: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    texts.extend(clean_text(paragraph.get("text", "")) for paragraph in extraction.get("paragraphs", []))
    texts.extend(clean_text(section.get("title", "")) for section in extraction.get("sections", []))
    texts.extend(clean_text(chapter.get("title", "")) for chapter in extraction.get("chapters", []))
    for visual in visual_manifest.get("visuals", []):
        texts.extend([clean_text(visual.get("name", "")), clean_text(visual.get("caption", ""))])
    for table in tables.get("tables", []):
        content = table.get("content", {})
        texts.append(clean_text(content.get("text", "")))
        for row in content.get("rows", []) or []:
            texts.append(clean_text(row.get("text", "")))
    return [text for text in texts if text]


def build_hierarchy(extraction: dict[str, Any], chapter_structure: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], dict[str, list[str]], dict[str, dict[str, Any]]]:
    """Build explicit Part -> Chapter -> Major section -> Subsection nodes."""
    page_map = build_page_map(chapter_structure)
    sections_by_chapter: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for section in extraction.get("sections", []):
        sections_by_chapter[int(section.get("chapter_number", 0))].append(section)
    paragraph_by_id = {paragraph.get("paragraph_id"): paragraph for paragraph in extraction.get("paragraphs", [])}
    chapter_meta = {
        int(chapter.get("chapter_number")): chapter
        for chapter in extraction.get("chapters", [])
        if chapter.get("chapter_number") is not None
    }
    parts: list[dict[str, Any]] = []
    all_nodes: dict[str, dict[str, Any]] = {}
    paragraph_to_leaf: dict[str, str] = {}
    paragraph_to_ancestors: dict[str, list[str]] = {}

    for part in chapter_structure.get("parts", []):
        part_number = int(part.get("part_number"))
        part_id = f"DAV25-PART{part_number:02d}"
        part_pdf_start = int(str(part.get("source_page_id", "")).replace("DAV25-PDF", ""))
        part_page = page_map.get(part_pdf_start, {})
        part_node = {
            "section_id": part_id,
            "level": "part",
            "part_number": part_number,
            "title": clean_text(part.get("title", "")),
            "pdf_page_start": part_pdf_start if part.get("source_page_id") else None,
            "printed_page_start": part_page.get("printed_page", part.get("printed_page_start")),
            "printed_page_end": None,
            "page_number_start": part_page.get("page_number", part.get("printed_page_start")),
            "page_number_end": None,
            "parent_id": None,
            "children": [],
            "chapter_ids": [],
            "paragraph_ids": [],
            "visual_ids": [],
            "table_ids": [],
            "concept_ids": [],
            "status": STATUS,
            "verification_status": STATUS,
        }
        all_nodes[part_id] = part_node
        parts.append(part_node)

        for chapter in part.get("chapters", []):
            chapter_number = int(chapter.get("chapter_number"))
            chapter_id = f"DAV25-CH{chapter_number:02d}"
            meta = chapter_meta.get(chapter_number, {})
            chapter_node = {
                "section_id": chapter_id,
                "level": "chapter",
                "chapter_number": chapter_number,
                "title": clean_text(chapter.get("title", "")),
                "part": part_node["title"],
                "pdf_page_start": meta.get("pdf_page_start", chapter.get("pdf_page_start")),
                "pdf_page_end": meta.get("pdf_page_end", chapter.get("pdf_page_end")),
                "printed_page_start": meta.get("printed_page_start", chapter.get("printed_page_start")),
                "printed_page_end": None,
                "page_number_start": meta.get("printed_page_start", chapter.get("printed_page_start")),
                "page_number_end": None,
                "parent_id": part_id,
                "children": [],
                "major_section_ids": [],
                "paragraph_ids": [],
                "visual_ids": [],
                "table_ids": [],
                "concept_ids": [],
                "status": STATUS,
                "verification_status": STATUS,
            }
            all_nodes[chapter_id] = chapter_node
            part_node["children"].append(chapter_id)
            part_node["chapter_ids"].append(chapter_id)
            part_node["chapter_ids"] = unique(part_node["chapter_ids"])

            entries = sorted(sections_by_chapter.get(chapter_number, []), key=lambda item: int(item.get("section_id", "0").replace("DAV25-SEC", "")))
            major_nodes: list[dict[str, Any]] = []
            current_major: dict[str, Any] | None = None
            major_index = 0
            sub_index_by_major: dict[str, int] = defaultdict(int)
            for entry_index, entry in enumerate(entries):
                level = int(entry.get("level", 1))
                if level == 1:
                    major_index += 1
                    major_id = f"{chapter_id}-M{major_index:02d}"
                    current_major = {
                        "section_id": major_id,
                        "source_section_id": entry.get("section_id"),
                        "level": "major_section",
                        "title": clean_text(entry.get("title", "")),
                        "part": part_node["title"],
                        "chapter_number": chapter_number,
                        "chapter_title": chapter_node["title"],
                        "pdf_page_start": entry.get("pdf_page_start"),
                        "printed_page_start": entry.get("printed_page_start"),
                        "printed_page_end": None,
                        "page_number_start": entry.get("printed_page_start"),
                        "page_number_end": None,
                        "parent_id": chapter_id,
                        "children": [],
                        "subsection_ids": [],
                        "direct_paragraph_ids": unique(entry.get("paragraph_ids", [])),
                        "paragraph_ids": [],
                        "visual_ids": [],
                        "table_ids": [],
                        "concept_ids": [],
                        "status": STATUS,
                        "verification_status": STATUS,
                    }
                    major_nodes.append(current_major)
                    all_nodes[major_id] = current_major
                    chapter_node["children"].append(major_id)
                    chapter_node["major_section_ids"].append(major_id)
                elif level == 2:
                    if current_major is None:
                        major_index += 1
                        major_id = f"{chapter_id}-M{major_index:02d}"
                        current_major = {
                            "section_id": major_id,
                            "source_section_id": None,
                            "level": "major_section",
                            "title": "Unassigned section content",
                            "part": part_node["title"],
                            "chapter_number": chapter_number,
                            "chapter_title": chapter_node["title"],
                            "pdf_page_start": entry.get("pdf_page_start"),
                            "printed_page_start": entry.get("printed_page_start"),
                            "printed_page_end": None,
                            "page_number_start": entry.get("printed_page_start"),
                            "page_number_end": None,
                            "parent_id": chapter_id,
                            "children": [],
                            "subsection_ids": [],
                            "direct_paragraph_ids": [],
                            "paragraph_ids": [],
                            "visual_ids": [],
                            "table_ids": [],
                            "concept_ids": [],
                            "status": STATUS,
                            "verification_status": STATUS,
                        }
                        major_nodes.append(current_major)
                        all_nodes[major_id] = current_major
                        chapter_node["children"].append(major_id)
                        chapter_node["major_section_ids"].append(major_id)
                    sub_index_by_major[current_major["section_id"]] += 1
                    sub_id = f"{current_major['section_id']}-S{sub_index_by_major[current_major['section_id']]:02d}"
                    subsection = {
                        "section_id": sub_id,
                        "source_section_id": entry.get("section_id"),
                        "level": "subsection",
                        "title": clean_text(entry.get("title", "")),
                        "part": part_node["title"],
                        "chapter_number": chapter_number,
                        "chapter_title": chapter_node["title"],
                        "pdf_page_start": entry.get("pdf_page_start"),
                        "printed_page_start": entry.get("printed_page_start"),
                        "printed_page_end": None,
                        "page_number_start": entry.get("printed_page_start"),
                        "page_number_end": None,
                        "parent_id": current_major["section_id"],
                        "children": [],
                        "direct_paragraph_ids": unique(entry.get("paragraph_ids", [])),
                        "paragraph_ids": unique(entry.get("paragraph_ids", [])),
                        "visual_ids": [],
                        "table_ids": [],
                        "concept_ids": [],
                        "status": STATUS,
                        "verification_status": STATUS,
                    }
                    all_nodes[sub_id] = subsection
                    current_major["children"].append(sub_id)
                    current_major["subsection_ids"].append(sub_id)

            # Calculate ranges and aggregate paragraph ownership.
            for index, major in enumerate(major_nodes):
                next_major_start = major_nodes[index + 1].get("pdf_page_start") if index + 1 < len(major_nodes) else chapter_node.get("pdf_page_end")
                major["pdf_page_end"] = (int(next_major_start) - 1) if next_major_start is not None else None
                if major.get("pdf_page_end") in page_map:
                    major["printed_page_end"] = page_map[int(major["pdf_page_end"])]["printed_page"]
                    major["page_number_end"] = major["printed_page_end"]
                for sub_index, sub_id in enumerate(major["subsection_ids"]):
                    sub = all_nodes[sub_id]
                    if sub_index + 1 < len(major["subsection_ids"]):
                        next_sub_start = all_nodes[major["subsection_ids"][sub_index + 1]].get("pdf_page_start")
                    else:
                        next_sub_start = next_major_start
                    sub["pdf_page_end"] = (int(next_sub_start) - 1) if next_sub_start is not None else None
                    if sub.get("pdf_page_end") in page_map:
                        sub["printed_page_end"] = page_map[int(sub["pdf_page_end"])]["printed_page"]
                        sub["page_number_end"] = sub["printed_page_end"]
                child_paragraphs = [pid for sub_id in major["subsection_ids"] for pid in all_nodes[sub_id].get("paragraph_ids", [])]
                major["paragraph_ids"] = unique(major.get("direct_paragraph_ids", []) + child_paragraphs)
                major["leaf_unit_id"] = major["section_id"] if not major["subsection_ids"] else None
                if major["subsection_ids"]:
                    for sub_id in major["subsection_ids"]:
                        for paragraph_id in all_nodes[sub_id]["paragraph_ids"]:
                            paragraph_to_leaf[paragraph_id] = sub_id
                for paragraph_id in major.get("direct_paragraph_ids", []):
                    paragraph_to_leaf[paragraph_id] = major["section_id"]

            chapter_node["paragraph_ids"] = unique(pid for major in major_nodes for pid in major.get("paragraph_ids", []))
            if chapter_node.get("pdf_page_end") in page_map:
                chapter_node["printed_page_end"] = page_map[int(chapter_node["pdf_page_end"])]["printed_page"]
                chapter_node["page_number_end"] = chapter_node["printed_page_end"]
            part_node["paragraph_ids"] = unique(part_node["paragraph_ids"] + chapter_node["paragraph_ids"])
            for paragraph_id in chapter_node["paragraph_ids"]:
                leaf_id = paragraph_to_leaf.get(paragraph_id)
                if not leaf_id:
                    continue
                ancestors = [leaf_id]
                parent_id = all_nodes[leaf_id].get("parent_id")
                while parent_id:
                    ancestors.append(parent_id)
                    parent_id = all_nodes.get(parent_id, {}).get("parent_id")
                paragraph_to_ancestors[paragraph_id] = ancestors

        chapter_ends = [node.get("pdf_page_end") for node in all_nodes.values() if node.get("parent_id") == part_id and node.get("level") == "chapter"]
        if chapter_ends:
            part_node["pdf_page_end"] = max(int(value) for value in chapter_ends if value is not None)
            if part_node["pdf_page_end"] in page_map:
                part_node["printed_page_end"] = page_map[int(part_node["pdf_page_end"])]["printed_page"]
                part_node["page_number_end"] = part_node["printed_page_end"]

    # Source pages and stable section paths.
    for node_id, node in all_nodes.items():
        paragraph_ids = node.get("paragraph_ids", [])
        page_ids = unique(
            page_id
            for paragraph_id in paragraph_ids
            for page_id in paragraph_by_id.get(paragraph_id, {}).get("source_page_ids", [])
        )
        node["source_page_ids"] = page_ids
        path_nodes = []
        cursor: dict[str, Any] | None = node
        while cursor:
            path_nodes.append(cursor.get("title", ""))
            cursor = all_nodes.get(cursor.get("parent_id"))
        node["section_path"] = list(reversed([value for value in path_nodes if value]))

    for node in all_nodes.values():
        for paragraph_id in node.get("paragraph_ids", []):
            if paragraph_id not in paragraph_to_ancestors:
                paragraph_to_ancestors[paragraph_id] = [node["section_id"]]

    def public_node(node: dict[str, Any]) -> dict[str, Any]:
        public = dict(node)
        public["paragraph_count"] = len(node.get("paragraph_ids", []))
        public["source_page_count"] = len(node.get("source_page_ids", []))
        # Paragraph ownership is stored once at leaf level. Parent nodes are
        # navigable through children and counts; repeating every descendant
        # paragraph ID made the structure file needlessly enormous.
        if node.get("level") in {"part", "chapter"} or (
            node.get("level") == "major_section" and node.get("subsection_ids")
        ):
            public.pop("paragraph_ids", None)
            public.pop("source_page_ids", None)
            public.pop("direct_paragraph_ids", None)
        return public

    public_parts = []
    for part in parts:
        public_part = public_node(part)
        public_part["children"] = list(part.get("children", []))
        public_parts.append(public_part)
    structure = {
        "schema_version": "vtc-davidson25.retrieval-structure.v1",
        "record_type": "retrieval_structure_lookup",
        "book_id": extraction.get("book_id"),
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "processing_order": ["subsection", "major_section", "chapter", "part"],
        "parts": public_parts,
        "nodes": [public_node(node) for node in all_nodes.values()],
        "counts": {
            "parts": len(parts),
            "chapters": sum(node.get("level") == "chapter" for node in all_nodes.values()),
            "major_sections": sum(node.get("level") == "major_section" for node in all_nodes.values()),
            "subsections": sum(node.get("level") == "subsection" for node in all_nodes.values()),
            "paragraphs": len(paragraph_by_id),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    return structure, paragraph_to_leaf, paragraph_to_ancestors, all_nodes


def visual_records(
    visual_manifest: dict[str, Any],
    tables: dict[str, Any],
    all_nodes: dict[str, dict[str, Any]],
    page_map: dict[int, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    page_map = page_map or {}
    table_by_visual = {table.get("visual_id"): table for table in tables.get("tables", [])}
    visual_entries: list[dict[str, Any]] = []
    visual_by_id: dict[str, dict[str, Any]] = {}
    chapters = [node for node in all_nodes.values() if node.get("level") == "chapter"]
    leaves = [node for node in all_nodes.values() if node.get("level") in {"subsection", "major_section"} and (node.get("level") == "subsection" or not node.get("subsection_ids"))]

    def page_number(item: dict[str, Any]) -> int | None:
        value = item.get("pdf_page")
        return int(value) if value is not None and str(value).isdigit() else None

    def choose_nodes(page: int | None, chapter_number: Any) -> list[dict[str, Any]]:
        candidates = [node for node in leaves if page is not None and node.get("pdf_page_start") is not None and node.get("pdf_page_end") is not None and int(node["pdf_page_start"]) <= page <= int(node["pdf_page_end"])]
        if chapter_number is not None:
            candidates = [node for node in candidates if int(node.get("chapter_number", -1)) == int(chapter_number)] or candidates
        if candidates:
            return sorted(candidates, key=lambda node: (len(node.get("section_path", [])), node["section_id"]))[:1]
        chapter_candidates = [node for node in chapters if chapter_number is not None and int(node.get("chapter_number", -1)) == int(chapter_number)]
        return chapter_candidates[:1]

    for visual in visual_manifest.get("visuals", []):
        visual_id = visual.get("visual_id")
        if not visual_id:
            continue
        page = page_number(visual)
        page_info = page_map.get(page, {}) if page is not None else {}
        chosen = choose_nodes(page, visual.get("chapter_number"))
        node_ids = [node["section_id"] for node in chosen]
        table = table_by_visual.get(visual_id)
        record = {
            "visual_id": visual_id,
            "table_id": visual.get("table_id"),
            "pdf_page": page,
            "page_number": page_info.get("page_number", visual.get("printed_page")),
            "printed_page": page_info.get("printed_page", visual.get("printed_page")),
            "source_page_id": page_info.get("source_page_id", visual.get("source_page_id")),
            "chapter_number": page_info.get("chapter_number", visual.get("chapter_number")),
            "chapter_title": page_info.get("chapter_title", visual.get("chapter_title")),
            "part": page_info.get("part"),
            "chapter_page_index": page_info.get("chapter_page_index"),
            "page_reference": page_info or {
                "source_page_id": visual.get("source_page_id"),
                "pdf_page": page,
                "page_number": visual.get("printed_page"),
                "printed_page": visual.get("printed_page"),
                "chapter_number": visual.get("chapter_number"),
                "chapter_title": visual.get("chapter_title"),
                "part": None,
                "chapter_page_index": None,
            },
            "visual_type": visual.get("visual_type"),
            "name": visual.get("name"),
            "caption": visual.get("caption"),
            "location": visual.get("location"),
            "policy": visual.get("policy"),
            "section_ids": node_ids,
            "section_paths": [node.get("section_path", []) for node in chosen],
            "table_reconstruction_available": bool(table),
            "table_reconstruction_source": "../../05 Visual Inventory/davidson25_tables_reconstructed_generated.json" if table else None,
            "status": STATUS,
            "verification_status": STATUS,
        }
        visual_entries.append(record)
        visual_by_id[visual_id] = record
        for node in chosen:
            node.setdefault("visual_ids", []).append(visual_id)
            if visual.get("table_id"):
                node.setdefault("table_ids", []).append(visual["table_id"])
    for node in all_nodes.values():
        node["visual_ids"] = unique(node.get("visual_ids", []))
        node["table_ids"] = unique(node.get("table_ids", []))
    return visual_entries, visual_by_id


def build_indexes(extraction: dict[str, Any], chapter_structure: dict[str, Any], visual_manifest: dict[str, Any], tables: dict[str, Any], analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    page_map = build_page_map(chapter_structure)
    structure, paragraph_to_leaf, paragraph_to_ancestors, all_nodes = build_hierarchy(extraction, chapter_structure)
    visual_entries, visual_by_id = visual_records(visual_manifest, tables, all_nodes, page_map)
    paragraph_by_id = {paragraph.get("paragraph_id"): paragraph for paragraph in extraction.get("paragraphs", [])}
    global_counts = Counter()
    for text in all_texts(extraction, visual_manifest, tables):
        for token in TOKEN_RE.findall(text):
            value = token_norm(token)
            if value and value not in GENERIC_EXCLUDE:
                global_counts[value] += 1

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    def add_source_candidates(*, text: str, source_kind: str, source_passage_ids: list[str], source_element_ids: list[str], source_page_ids: list[str], section_ids: list[str]) -> None:
        for (category, term_key), forms in token_candidates(text, global_counts, source_kind=source_kind).items():
            preferred_form = display_form(forms, term_key)
            grouped[(category, term_key)].append({
                "source_form": preferred_form,
                "source_passage_ids": unique(source_passage_ids),
                "source_element_ids": unique(source_element_ids),
                "source_page_ids": unique(source_page_ids),
                "section_ids": unique(section_ids),
                "source_excerpt": sentence_excerpt(text, preferred_form),
                "related_visual_ids": [element_id for element_id in source_element_ids if element_id in visual_by_id],
            })

    analysis_paragraphs = {
        item.get("source_passage_ids", [""])[0]: item
        for item in (analysis or {}).get("paragraph_extractions", [])
        if item.get("source_passage_ids")
    }

    def add_analysis_records(records: Iterable[dict[str, Any]], *, default_source_kind: str, default_passage_ids: list[str], default_element_ids: list[str], default_page_ids: list[str], default_section_ids: list[str]) -> None:
        for record in records:
            category = clean_text(record.get("category", "general_medical_terms")) or "general_medical_terms"
            preferred = clean_text(record.get("canonical_candidate")) or clean_text(record.get("source_form")) or clean_text(record.get("text_as_seen"))
            term_key = normalize(preferred)
            if not term_key:
                continue
            record_passage_ids = record.get("source_passage_ids", []) or (
                [record.get("source_passage_id")] if record.get("source_passage_id") else []
            )
            record_element_ids = record.get("source_element_ids", []) or (
                [record.get("source_element_id")] if record.get("source_element_id") else []
            )
            grouped[(category, term_key)].append({
                "source_form": clean_text(record.get("source_form")) or preferred,
                "source_passage_ids": unique(record_passage_ids or default_passage_ids),
                "source_element_ids": unique(record_element_ids or default_element_ids),
                "source_page_ids": unique(record.get("source_page_ids", []) or default_page_ids),
                "section_ids": unique(record.get("section_ids", []) or default_section_ids),
                "source_excerpt": clean_text(record.get("original_quotation")) or clean_text(record.get("source_excerpt")) or preferred,
                "related_visual_ids": unique(record.get("related_visual_ids", [])),
                "retrieval_terms": unique(record.get("retrieval_terms", [])),
            })

    if analysis:
        for paragraph_id, paragraph in paragraph_by_id.items():
            analysis_record = analysis_paragraphs.get(paragraph_id, {})
            add_analysis_records(
                analysis_record.get("keyword_records", []),
                default_source_kind="paragraph",
                default_passage_ids=[paragraph_id],
                default_element_ids=[],
                default_page_ids=paragraph.get("source_page_ids", []),
                default_section_ids=paragraph_to_ancestors.get(paragraph_id, []),
            )
        add_analysis_records(
            analysis.get("section_keyword_records", []),
            default_source_kind="section",
            default_passage_ids=[],
            default_element_ids=[],
            default_page_ids=[],
            default_section_ids=[],
        )
    else:
        for paragraph_id, paragraph in paragraph_by_id.items():
            ancestors = paragraph_to_ancestors.get(paragraph_id, [])
            add_source_candidates(
                text=paragraph.get("text", ""),
                source_kind="paragraph",
                source_passage_ids=[paragraph_id],
                source_element_ids=[],
                source_page_ids=paragraph.get("source_page_ids", []),
                section_ids=ancestors,
            )

    # Headings are explicit retrieval anchors. They link to the node's own
    # paragraphs but do not introduce a separate summary or claims layer.
    if not analysis:
        for node in all_nodes.values():
            title = clean_text(node.get("title", ""))
            if not title:
                continue
            node_ancestors = []
            cursor: dict[str, Any] | None = node
            while cursor:
                node_ancestors.append(cursor["section_id"])
                cursor = all_nodes.get(cursor.get("parent_id"))
            grouped[("section_topics", normalize(title))].append({
                "source_form": title,
                "source_passage_ids": node.get("paragraph_ids", []),
                "source_element_ids": [node["section_id"]],
                "source_page_ids": node.get("source_page_ids", []),
                "section_ids": node_ancestors,
                "source_excerpt": title,
                "related_visual_ids": node.get("visual_ids", []),
                "retrieval_terms": [title],
            })

    table_records_by_id = {table.get("table_id"): table for table in tables.get("tables", [])}
    for visual in visual_entries:
        table = table_records_by_id.get(visual.get("table_id"))
        content = table.get("content", {}) if table else {}
        visual_text = clean_text(" ".join(value for value in (visual.get("name"), visual.get("caption"), content.get("text")) if value))
        if not visual_text:
            continue
        if analysis:
            visual_records_for_id = [
                item for item in (analysis.get("visual_extractions", []) or [])
                if item.get("source_element_id") in {visual["visual_id"], visual.get("table_id")}
            ]
            add_analysis_records(
                visual_records_for_id,
                default_source_kind="visual",
                default_passage_ids=[],
                default_element_ids=unique([visual["visual_id"], visual.get("table_id", "")]),
                default_page_ids=[visual.get("source_page_id", "")],
                default_section_ids=unique(visual.get("section_ids", [])),
            )
        else:
            add_source_candidates(
                text=visual_text,
                source_kind="visual",
                source_passage_ids=[],
                source_element_ids=unique([visual["visual_id"], visual.get("table_id", "")]),
                source_page_ids=[visual.get("source_page_id", "")],
                section_ids=unique(visual.get("section_ids", [])),
            )

    concepts: list[dict[str, Any]] = []
    occurrences: list[dict[str, Any]] = []
    for index, ((category, term_key), records) in enumerate(sorted(grouped.items()), 1):
        concept_id = f"DAV25-C-{index:07d}"
        source_forms = unique(record["source_form"] for record in records)
        preferred = display_form(source_forms, term_key)
        retrieval_terms = unique(
            alias
            for value in [preferred] + source_forms + [term for record in records for term in record.get("retrieval_terms", [])]
            for alias in alias_variants(value)
        )
        occurrence_ids: list[str] = []
        section_ids: list[str] = []
        for occurrence_index, record in enumerate(records, 1):
            occurrence_id = f"DAV25-O-{len(occurrences) + 1:08d}"
            occurrence_ids.append(occurrence_id)
            section_ids.extend(record.get("section_ids", []))
            occurrences.append({
                "occurrence_id": occurrence_id,
                "concept_id": concept_id,
                "category": category,
                "broad_area": CATEGORY_LABELS.get(category, category),
                "small_area": preferred,
                "keyword_path": [CATEGORY_LABELS.get(category, category), preferred],
                "source_form": record["source_form"],
                "source_passage_ids": unique(record.get("source_passage_ids", [])),
                "source_element_ids": unique(record.get("source_element_ids", [])),
                "source_page_ids": unique(record.get("source_page_ids", [])),
                "source_pages": page_refs(record.get("source_page_ids", []), page_map),
                "section_ids": unique(record.get("section_ids", [])),
                "source_excerpt": record.get("source_excerpt", ""),
                "related_visual_ids": unique(record.get("related_visual_ids", [])),
                "retrieval_terms": retrieval_terms,
                "status": STATUS,
                "verification_status": STATUS,
            })
        concept = {
            "concept_id": concept_id,
            "category": category,
            "broad_area": CATEGORY_LABELS.get(category, category),
            "preferred_label": preferred,
            "canonical_candidate": preferred,
            "keyword_path": [CATEGORY_LABELS.get(category, category), preferred],
            "source_forms": source_forms,
            "retrieval_terms": retrieval_terms,
            "occurrence_ids": occurrence_ids,
            "occurrence_count": len(occurrence_ids),
            "section_ids": unique(section_ids),
            "status": STATUS,
            "verification_status": STATUS,
        }
        concepts.append(concept)
        for section_id in unique(section_ids):
            if section_id in all_nodes:
                all_nodes[section_id].setdefault("concept_ids", []).append(concept_id)

    for node in all_nodes.values():
        node["concept_ids"] = unique(node.get("concept_ids", []))
    structure_nodes = {node["section_id"]: node for node in structure.get("nodes", [])}
    for node_id, public_node in structure_nodes.items():
        internal_node = all_nodes.get(node_id)
        if internal_node:
            public_node["concept_ids"] = unique(internal_node.get("concept_ids", []))
    public_parts = {part["section_id"]: part for part in structure.get("parts", [])}
    for part_id, public_part in public_parts.items():
        internal_part = all_nodes.get(part_id)
        if internal_part:
            public_part["concept_ids"] = unique(internal_part.get("concept_ids", []))
    concept_by_id = {concept["concept_id"]: concept for concept in concepts}
    term_map: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"display_forms": set(), "concept_ids": set(), "occurrence_ids": set(), "categories": set()})
    for concept in concepts:
        for term in concept["retrieval_terms"]:
            term_key = normalize(term)
            if not term_key:
                continue
            entry = term_map[term_key]
            entry["display_forms"].add(term)
            entry["concept_ids"].add(concept["concept_id"])
            entry["occurrence_ids"].update(concept["occurrence_ids"])
            entry["categories"].add(concept["category"])
    term_entries = {
        term: {
            "display_forms": sorted(entry["display_forms"]),
            "concept_ids": sorted(entry["concept_ids"]),
            "occurrence_ids": sorted(entry["occurrence_ids"]),
            "categories": sorted(entry["categories"]),
        }
        for term, entry in sorted(term_map.items())
    }

    passage_lines: list[dict[str, Any]] = []
    for paragraph_id, paragraph in paragraph_by_id.items():
        leaf_id = paragraph_to_leaf.get(paragraph_id)
        ancestors = paragraph_to_ancestors.get(paragraph_id, [])
        path = all_nodes.get(leaf_id, {}).get("section_path", []) if leaf_id else []
        passage_lines.append({
            "source_passage_id": paragraph_id,
            "text": paragraph.get("text", ""),
            "source_page_ids": paragraph.get("source_page_ids", []),
            "source_pages": page_refs(paragraph.get("source_page_ids", []), page_map),
            "section_ids": ancestors,
            "section_path": path,
            "content_type": paragraph.get("content_type", "logical_text_block"),
            "status": STATUS,
            "verification_status": STATUS,
        })

    concept_index = {
        "schema_version": "llm-wiki.concept-index.v1-medical",
        "record_type": "concept_index",
        "book_id": extraction.get("book_id"),
        "index_rule": "Group by medical category + normalized candidate; retain source forms, broad-to-small keyword path, aliases, and occurrence IDs.",
        "keyword_taxonomy": CATEGORY_LABELS,
        "concepts": concepts,
        "counts": {
            "concepts": len(concepts),
            "occurrences": len(occurrences),
            "categories": len({concept["category"] for concept in concepts}),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    occurrence_index = {
        "schema_version": "llm-wiki.occurrence-index.v1-medical",
        "record_type": "occurrence_index",
        "book_id": extraction.get("book_id"),
        "index_rule": "Each occurrence points to a concept, source passage or visual element, and explicit section path; no relationship inference is performed.",
        "occurrences": occurrences,
        "counts": {
            "occurrences": len(occurrences),
            "passage_occurrences": sum(bool(item["source_passage_ids"]) for item in occurrences),
            "visual_occurrences": sum(bool(item["source_element_ids"]) for item in occurrences),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    term_lookup = {
        "schema_version": "llm-wiki.term-lookup-index.v1-medical",
        "record_type": "term_lookup_index",
        "book_id": extraction.get("book_id"),
        "normalization": "Unicode NFKC + casefold + letters/digits only; aliases include selected UK/US spellings and simple singular variants.",
        "lookup_rule": "Exact normalized terms and query substrings return candidate concepts and occurrences; the AI must read the linked source units.",
        "terms": term_entries,
        "counts": {
            "terms": len(term_entries),
            "concepts_referenced": len(concept_by_id),
            "occurrences_referenced": len(occurrences),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    visual_index = {
        "schema_version": "vtc-davidson25.visual-retrieval-index.v1",
        "record_type": "visual_retrieval_index",
        "book_id": extraction.get("book_id"),
        "policy": {
            "tables": "full reconstructed contents remain in the visual table layer and are returned by the query helper when matched",
            "non_tables": "metadata, name/caption, page, location, and caption-derived terms only",
        },
        "visuals": visual_entries,
        "counts": {
            "visuals": len(visual_entries),
            "tables": sum(bool(item.get("table_id")) for item in visual_entries),
            "non_tables": sum(not bool(item.get("table_id")) for item in visual_entries),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    concept_id_set = set(concept_by_id)
    occurrence_id_set = {occurrence["occurrence_id"] for occurrence in occurrences}
    validation = {
        "schema_version": "llm-wiki.medical-retrieval-validation.v1",
        "record_type": "retrieval_index_validation_report",
        "book_id": extraction.get("book_id"),
        "checks": {
            "no_claims_index_requested": True,
            "concept_ids_unique": len({item["concept_id"] for item in concepts}) == len(concepts),
            "occurrence_ids_unique": len({item["occurrence_id"] for item in occurrences}) == len(occurrences),
            "occurrence_concept_links_resolve": all(item["concept_id"] in concept_by_id for item in occurrences),
            "term_concept_links_resolve": all(set(item["concept_ids"]) <= concept_id_set for item in term_entries.values()),
            "term_occurrence_links_resolve": all(set(item["occurrence_ids"]) <= occurrence_id_set for item in term_entries.values()),
            "paragraphs_have_portable_source_records": len(passage_lines) == len(paragraph_by_id),
            "passage_page_references_resolve": all(
                page.get("pdf_page") in page_map
                and page.get("page_number") is not None
                for passage in passage_lines
                for page in passage.get("source_pages", [])
            ),
            "visual_page_numbers_match_source_map": all(
                visual.get("page_number") == page_map.get(visual.get("pdf_page"), {}).get("page_number")
                for visual in visual_entries
                if visual.get("pdf_page") in page_map
            ),
            "paragraph_section_links_resolve": all(section_id in all_nodes for passage in passage_lines for section_id in passage["section_ids"]),
            "occurrence_passage_links_resolve": all(source_id in paragraph_by_id for item in occurrences for source_id in item["source_passage_ids"]),
            "occurrence_element_links_resolve": all(source_id in visual_by_id or source_id in table_records_by_id or source_id in all_nodes for item in occurrences for source_id in item["source_element_ids"]),
            "section_concept_links_resolve": all(concept_id in concept_by_id for node in all_nodes.values() for concept_id in node["concept_ids"]),
            "generated_not_verified_preserved": all(item.get("verification_status") == STATUS for item in concepts + occurrences + passage_lines + visual_entries),
        },
        "counts": {
            "parts": structure["counts"]["parts"],
            "chapters": structure["counts"]["chapters"],
            "major_sections": structure["counts"]["major_sections"],
            "subsections": structure["counts"]["subsections"],
            "paragraphs": len(passage_lines),
            "concepts": len(concepts),
            "occurrences": len(occurrences),
            "terms": len(term_map),
            "visuals": len(visual_entries),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    return {
        "structure": structure,
        "concept_index": concept_index,
        "occurrence_index": occurrence_index,
        "term_lookup": term_lookup,
        "visual_index": visual_index,
        "validation": validation,
        "passage_lines": passage_lines,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction", required=True, type=Path)
    parser.add_argument("--structure", required=True, type=Path)
    parser.add_argument("--visual-manifest", required=True, type=Path)
    parser.add_argument("--tables", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--analysis", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output_root.exists() and not args.overwrite:
        raise SystemExit(f"Output exists; pass --overwrite: {args.output_root}")
    args.output_root.mkdir(parents=True, exist_ok=True)
    extraction = load_json(args.extraction)
    chapter_structure = load_json(args.structure)
    visual_manifest = load_json(args.visual_manifest)
    tables = load_json(args.tables)
    analysis = load_json(args.analysis) if args.analysis else None
    if analysis and analysis.get("record_type") != "paragraph_first_analysis":
        raise SystemExit("--analysis must be record_type=paragraph_first_analysis")
    result = build_indexes(extraction, chapter_structure, visual_manifest, tables, analysis=analysis)
    for filename, key in (
        ("structure_lookup.json", "structure"),
        ("concept_index.json", "concept_index"),
        ("occurrence_index.json", "occurrence_index"),
        ("term_lookup.json", "term_lookup"),
        ("visual_index.json", "visual_index"),
        ("retrieval_index_validation_report.json", "validation"),
    ):
        (args.output_root / filename).write_text(json.dumps(result[key], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (args.output_root / "passage_index.jsonl").open("w", encoding="utf-8") as handle:
        for line in result["passage_lines"]:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(json.dumps({"output_root": str(args.output_root), "counts": result["validation"]["counts"], "checks": result["validation"]["checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
