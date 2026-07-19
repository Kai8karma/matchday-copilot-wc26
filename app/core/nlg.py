"""Template-based natural language generation (the zero-API-key path).

Every intent has en/es/fr templates. When an LLM provider is configured,
app/llm.py rewrites these grounded drafts for fluency; when it is not, the
templates ARE the answer — so the assistant is fully functional offline.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.core.engine import Decision
from app.models import AssistRequest, Intent, Language

_DATA = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def knowledge() -> dict[str, str]:
    return json.loads((_DATA / "knowledge.json").read_text(encoding="utf-8"))


_FAQ_TOPICS: dict[str, tuple[str, ...]] = {
    "bag_policy": ("bag", "bags", "bolsa", "sac"),
    "prohibited_items": ("prohibited", "allowed", "rules", "policy", "regle"),
    "re_entry": ("re-entry", "reentry", "leave and come"),
    "water": ("water", "refill", "agua", "eau"),
    "lost_and_found": ("lost", "found", "perdido", "perdu"),
    "parking": ("parking", "park", "car", "transit"),
    "tickets": ("ticket", "tickets", "boleto", "billet", "transfer"),
    "children": ("child", "children", "kids", "family"),
    "smoking": ("smoking", "smoke", "cigarette", "vape"),
    "weather": ("weather", "rain", "lightning", "storm"),
}


def faq_answer(message: str) -> str | None:
    lowered = message.lower()
    for key, terms in _FAQ_TOPICS.items():
        if any(t in lowered for t in terms):
            return knowledge()[key]
    return None


_T: dict[Intent, dict[Language, str]] = {
    Intent.MEDICAL: {
        Language.EN: (
            "This is being treated as a medical emergency. Go to (or direct "
            "responders to) {station}. A medical team has been alerted — stay "
            "on the line and keep the area clear."
        ),
        Language.ES: (
            "Esto se trata como una emergencia médica. Acude a {station}. Un "
            "equipo médico ha sido alertado; mantén el área despejada."
        ),
        Language.FR: (
            "Ceci est traité comme une urgence médicale. Rendez-vous à "
            "{station}. Une équipe médicale a été alertée ; gardez la zone dégagée."
        ),
    },
    Intent.SECURITY: {
        Language.EN: (
            "Thanks for reporting this — it has been logged as {priority}. "
            "Stewards are being directed to your area. Do not intervene "
            "yourself; keep a safe distance."
        ),
        Language.ES: (
            "Gracias por reportarlo: registrado como {priority}. Personal de "
            "seguridad va en camino. No intervengas; mantén distancia."
        ),
        Language.FR: (
            "Merci du signalement : enregistré en {priority}. Des stadiers "
            "arrivent. N'intervenez pas ; restez à distance."
        ),
    },
    Intent.NAVIGATION: {
        Language.EN: (
            "Head to {gate} ({gate_name}) — current load {load}. "
            "{step_free_note}"
        ),
        Language.ES: (
            "Dirígete a {gate} ({gate_name}); carga actual {load}. "
            "{step_free_note}"
        ),
        Language.FR: (
            "Dirigez-vous vers {gate} ({gate_name}) ; affluence actuelle "
            "{load}. {step_free_note}"
        ),
    },
    Intent.EGRESS: {
        Language.EN: (
            "Best exit right now: {gate} ({gate_name}), load {load}. {surge_note}"
        ),
        Language.ES: (
            "Mejor salida ahora: {gate} ({gate_name}), carga {load}. {surge_note}"
        ),
        Language.FR: (
            "Meilleure sortie actuellement : {gate} ({gate_name}), affluence "
            "{load}. {surge_note}"
        ),
    },
    Intent.FOOD: {
        Language.EN: (
            "Shortest queue near you: {stand} in the {zone} zone "
            "(~{queue} people). Menu: {menu}."
        ),
        Language.ES: (
            "La fila más corta cerca de ti: {stand} en la zona {zone} "
            "(~{queue} personas). Menú: {menu}."
        ),
        Language.FR: (
            "File la plus courte près de vous : {stand}, zone {zone} "
            "(~{queue} personnes). Menu : {menu}."
        ),
    },
    Intent.CROWD: {
        Language.EN: "Live crowd picture: {summary}. {hot_note}",
        Language.ES: "Situación de aforo en vivo: {summary}. {hot_note}",
        Language.FR: "Situation d'affluence en direct : {summary}. {hot_note}",
    },
    Intent.MATCH_INFO: {
        Language.EN: (
            "Next match here: {home} vs {away} ({stage}), kickoff {kickoff}. "
            "Gates open {gates_open}."
        ),
        Language.ES: (
            "Próximo partido aquí: {home} vs {away} ({stage}), inicio "
            "{kickoff}. Puertas abren {gates_open}."
        ),
        Language.FR: (
            "Prochain match ici : {home} vs {away} ({stage}), coup d'envoi "
            "{kickoff}. Ouverture des portes {gates_open}."
        ),
    },
    Intent.ACCESSIBILITY: {
        Language.EN: (
            "Step-free gates: {gates}. Wheelchair seating: {seating} zones. "
            "{sensory}. For anything else, the {desk} can help."
        ),
        Language.ES: (
            "Puertas sin escalones: {gates}. Asientos para silla de ruedas: "
            "zonas {seating}. {sensory}. Para más ayuda: {desk}."
        ),
        Language.FR: (
            "Portes sans marches : {gates}. Places fauteuil roulant : zones "
            "{seating}. {sensory}. Pour toute aide : {desk}."
        ),
    },
    Intent.FAQ: {
        Language.EN: "{answer}",
        Language.ES: "{answer}",
        Language.FR: "{answer}",
    },
    Intent.UNKNOWN: {
        Language.EN: (
            "I can help with directions and gates, exits, food queues, match "
            "info, accessibility, venue rules, and reporting incidents. What "
            "do you need?"
        ),
        Language.ES: (
            "Puedo ayudarte con direcciones y puertas, salidas, filas de "
            "comida, información del partido, accesibilidad, normas del "
            "estadio y reportar incidentes. ¿Qué necesitas?"
        ),
        Language.FR: (
            "Je peux aider : itinéraires et portes, sorties, files de "
            "restauration, infos match, accessibilité, règlement du stade et "
            "signalement d'incidents. Que vous faut-il ?"
        ),
    },
}

_STEP_FREE = {
    Language.EN: "This gate is step-free.",
    Language.ES: "Esta puerta no tiene escalones.",
    Language.FR: "Cette porte est sans marches.",
}
_SURGE = {
    Language.EN: (
        "Your zone is very busy — consider waiting ~10 minutes or using the "
        "suggested alternate route to avoid the crush."
    ),
    Language.ES: (
        "Tu zona está muy llena: espera ~10 minutos o usa la ruta alternativa "
        "sugerida para evitar aglomeraciones."
    ),
    Language.FR: (
        "Votre zone est très chargée : attendez ~10 minutes ou prenez "
        "l'itinéraire alternatif pour éviter la cohue."
    ),
}
_HOT = {
    Language.EN: "Interventions recommended — see actions.",
    Language.ES: "Se recomiendan intervenciones; ver acciones.",
    Language.FR: "Interventions recommandées — voir actions.",
}
_CALM = {
    Language.EN: "All zones within safe limits.",
    Language.ES: "Todas las zonas dentro de límites seguros.",
    Language.FR: "Toutes les zones sont dans les limites de sécurité.",
}
_NO_MATCH = {
    Language.EN: "No further matches are scheduled at this stadium.",
    Language.ES: "No hay más partidos programados en este estadio.",
    Language.FR: "Aucun autre match n'est programmé dans ce stade.",
}


def _slots(decision: Decision, req: AssistRequest, lang: Language) -> dict[str, str]:
    f = decision.facts
    slots: dict[str, str] = {"priority": decision.priority.value}
    if "station" in f:
        slots["station"] = f["station"]["name"]
    gate = f.get("gate")
    if gate:
        slots.update(
            gate=gate["id"],
            gate_name=gate["name"],
            load=f"{gate['load']:.0%}",
            step_free_note=_STEP_FREE[lang] if gate["step_free"] else "",
            surge_note=_SURGE[lang] if f.get("surge") else "",
        )
    stand = f.get("stand")
    if stand:
        slots.update(
            stand=stand["name"],
            zone=stand["zone"],
            queue=str(stand["queue"]),
            menu=stand["menu"],
        )
    if "zones" in f:
        slots["summary"] = ", ".join(
            f"{z['id']} {z['occupancy']:.0%}" for z in f["zones"]
        )
        slots["hot_note"] = _HOT[lang] if f.get("hot") else _CALM[lang]
    match = f.get("match")
    if decision.intent is Intent.MATCH_INFO:
        if match:
            slots.update(
                home=match["home"],
                away=match["away"],
                stage=match["stage"],
                kickoff=match["kickoff"],
                gates_open=match["gates_open"],
            )
        else:
            return {"__override__": _NO_MATCH[lang]}
    acc = f.get("accessibility")
    if acc:
        slots.update(
            gates=", ".join(acc["step_free_gates"]),
            seating=", ".join(acc["wheelchair_seating_zones"]),
            sensory=acc["sensory_room"]["name"],
            desk=acc["assistance_desk"]["name"],
        )
    if decision.intent is Intent.FAQ:
        slots["answer"] = faq_answer(req.message) or _T[Intent.UNKNOWN][lang]
    return slots


def render(decision: Decision, req: AssistRequest) -> str:
    """Fill the intent/language template with live facts."""
    lang = req.language
    slots = _slots(decision, req, lang)
    if "__override__" in slots:
        return slots["__override__"]
    text = _T[decision.intent][lang].format_map(_Safe(slots))
    return re.sub(r"\s{2,}", " ", text).strip()


class _Safe(dict):
    def __missing__(self, key: str) -> str:  # pragma: no cover - safety net
        return ""
