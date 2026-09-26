"""Synthetic entity vocabulary used by mock AI components and context resolution.

All products are FICTIONAL. Keep in sync with data/seed/.
"""

from app.schemas.enums import EntityType

PRODUCTS: tuple[str, ...] = ("Novara", "Cardexa", "Lumetrex")

# canonical name -> (entity type, lowercase aliases)
ENTITY_ALIASES: dict[str, tuple[EntityType, tuple[str, ...]]] = {
    "renal impairment": (EntityType.POPULATION, ("renal", "kidney", "renal impairment", "egfr")),
    "hepatic impairment": (EntityType.POPULATION, ("hepatic", "liver")),
    "dosing": (EntityType.TOPIC, ("dose", "dosing", "dosage", "titration")),
    "long-term outcomes": (EntityType.TOPIC, ("long-term", "long term", "follow-up", "durability")),
    "patient access": (EntityType.TOPIC, ("access", "coverage", "prior authorization", "copay", "insurance")),
    "safety": (EntityType.TOPIC, ("safety", "adverse", "side effect", "tolerability")),
    "efficacy": (EntityType.TOPIC, ("efficacy", "response rate", "endpoint", "results")),
    "adherence": (EntityType.TOPIC, ("adherence", "compliance")),
    "HER2": (EntityType.BIOMARKER, ("her2",)),
    "heart failure": (EntityType.CONDITION, ("heart failure", "hf", "condition h")),
    "Condition X": (EntityType.CONDITION, ("condition x",)),
    "Condition Z": (EntityType.CONDITION, ("condition z",)),
}
