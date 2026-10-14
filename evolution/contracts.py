"""JSON contracts used by the evolutionary narrative pipeline."""


CHARACTER_SCHEMA = {
    "type": "object",
    "required": [
        "id",
        "name",
        "gender",
        "is_protagonist",
        "personality",
        "appearance",
        "background",
        "desire",
        "fear",
        "secret",
    ],
    "additionalProperties": True,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "gender": {"type": "string"},
        "is_protagonist": {"type": "boolean"},
        "personality": {"type": "string"},
        "appearance": {"type": "string"},
        "background": {"type": "string"},
        "desire": {"type": "string"},
        "fear": {"type": "string"},
        "secret": {"type": "string"},
        "speech_style": {"type": "string"},
    },
}


SCENE_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "description"],
    "additionalProperties": True,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 1},
    },
}


CORE_GDD_SCHEMA = {
    "type": "object",
    "required": [
        "schema_version",
        "title",
        "background",
        "art_style",
        "themes",
        "world_rules",
        "immutable_facts",
        "initial_conflict",
        "ending_conditions",
        "characters",
        "scenes",
        "initial_world_state",
        "initial_agenda",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "const": "evo-gdd/1.0"},
        "title": {"type": "string", "minLength": 1},
        "background": {"type": "string", "minLength": 1},
        "art_style": {"type": "string", "minLength": 1},
        "themes": {"type": "array", "items": {"type": "string"}},
        "world_rules": {"type": "array", "items": {"type": "string"}},
        "immutable_facts": {"type": "array", "items": {"type": "string"}},
        "initial_conflict": {"type": "string", "minLength": 1},
        "ending_conditions": {"type": "array", "items": {"type": "string"}},
        "characters": {
            "type": "array",
            "minItems": 1,
            "items": CHARACTER_SCHEMA,
        },
        "scenes": {
            "type": "array",
            "minItems": 1,
            "items": SCENE_SCHEMA,
        },
        "initial_world_state": {"type": "object"},
        "initial_agenda": {
            "type": "object",
            "required": [
                "open_questions",
                "unresolved_conflicts",
                "foreshadowing",
                "character_arcs",
            ],
            "additionalProperties": True,
            "properties": {
                "open_questions": {"type": "array", "items": {"type": "string"}},
                "unresolved_conflicts": {"type": "array", "items": {"type": "string"}},
                "foreshadowing": {"type": "array", "items": {"type": "string"}},
                "character_arcs": {"type": "object"},
            },
        },
    },
}


NODE_CONTRACT_SCHEMA = {
    "type": "object",
    "required": [
        "goal",
        "dramatic_question",
        "active_cast",
        "location",
        "required_outcomes",
        "forbidden_outcomes",
    ],
    "additionalProperties": False,
    "properties": {
        "goal": {"type": "string", "minLength": 1},
        "dramatic_question": {"type": "string", "minLength": 1},
        "active_cast": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "location": {"type": "string", "minLength": 1},
        "required_outcomes": {"type": "array", "items": {"type": "string"}},
        "forbidden_outcomes": {"type": "array", "items": {"type": "string"}},
    },
}


STATE_TRANSITION_SCHEMA = {
    "type": "object",
    "required": ["summary", "goal_completed", "updates", "agenda"],
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string", "minLength": 1},
        "goal_completed": {"type": "boolean"},
        "updates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "value", "evidence"],
                "additionalProperties": False,
                "properties": {
                    "path": {
                        "type": "string",
                        "pattern": "^[a-zA-Z0-9_-]+(?:\\.[a-zA-Z0-9_-]+)*$",
                    },
                    "value": {},
                    "evidence": {"type": "string"},
                },
            },
        },
        "agenda": {"type": "object"},
    },
}


EXPANSION_SCHEMA = {
    "type": "object",
    "required": ["story_complete", "completion_reason", "next_nodes"],
    "additionalProperties": False,
    "properties": {
        "story_complete": {"type": "boolean"},
        "completion_reason": {"type": "string"},
        "next_nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["choice_text", "contract"],
                "additionalProperties": False,
                "properties": {
                    "choice_text": {"type": "string", "minLength": 1},
                    "contract": NODE_CONTRACT_SCHEMA,
                },
            },
        },
    },
}
