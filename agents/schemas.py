"""
JSON Schemas for agent message contracts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
用于约束核心中间产物的结构，降低多 Agent 协作中的字段漂移。
"""

GAME_OUTLINE_SCHEMA = {
    "type": "object",
    "required": ["title", "background", "art_style", "story_outline", "characters", "scenes"],
    "additionalProperties": True,
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "background": {"type": "string", "minLength": 1},
        "art_style": {"type": "string", "minLength": 1},
        "story_outline": {
            "type": "object",
            "required": ["groups"],
            "properties": {
                "groups": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["group_id", "group_outline"],
                        "properties": {
                            "group_id": {"type": "string", "minLength": 1},
                            "group_outline": {"type": "string", "minLength": 1}
                        }
                    }
                }
            }
        },
        "characters": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "name", "gender", "is_protagonist", "personality", "appearance", "background"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "name": {"type": "string", "minLength": 1},
                    "gender": {"type": "string"},
                    "is_protagonist": {"type": "boolean"},
                    "personality": {"type": "string"},
                    "appearance": {"type": "string"},
                    "background": {"type": "string"}
                }
            }
        },
        "scenes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "name", "description"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "name": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1}
                }
            }
        }
    }
}


STORY_GRAPH_SCHEMA = {
    "type": "object",
    "required": ["nodes", "edges"],
    "additionalProperties": True,
    "properties": {
        "nodes": {
            "type": "object",
            "minProperties": 1,
            "required": ["root"],
            "additionalProperties": {
                "type": "object",
                "required": ["id", "summary", "type"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "summary": {"type": "string", "minLength": 1},
                    "type": {"type": "string", "enum": ["normal", "merge"]}
                }
            }
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["from", "to", "choice_text"],
                "properties": {
                    "from": {"type": "string", "minLength": 1},
                    "to": {"type": "string", "minLength": 1},
                    "choice_text": {"type": ["string", "null"]}
                }
            }
        }
    }
}


PLOT_SEGMENTS_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "required": ["id", "summary", "characters", "location"],
        "properties": {
            "id": {"type": ["integer", "string"]},
            "summary": {"type": "string", "minLength": 1},
            "characters": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1}
            },
            "location": {"type": "string", "minLength": 1}
        }
    }
}


PRODUCER_REACT_STEP_SCHEMA = {
    "type": "object",
    "required": ["thought", "action", "action_input"],
    "additionalProperties": True,
    "properties": {
        "thought": {"type": "string", "minLength": 1},
        "action": {
            "type": "string",
            "enum": ["graph_validate", "enumerate_paths", "finalize"]
        },
        "action_input": {
            "type": "object",
            "additionalProperties": True,
        },
        "final_decision": {"type": "string"},
        "final_feedback": {"type": "string"}
    }
}


ACTOR_IMAGE_CRITIQUE_SCHEMA = {
    "type": "object",
    "required": ["decision", "feedback"],
    "additionalProperties": True,
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["PASS", "REVISE"]
        },
        "feedback": {
            "type": "string"
        }
    }
}
