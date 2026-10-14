"""
JSON Schemas for agent message contracts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
用于约束核心中间产物的结构，降低多 Agent 协作中的字段漂移。
"""


CORE_GDD_SCHEMA = {
    "type": "object",
    "required": [
        "schema_version", "title", "background", "art_style", "themes",
        "world_rules", "immutable_facts", "initial_conflict",
        "global_goal", "ending_conditions", "characters", "scenes",
        "initial_world_state", "initial_agenda"
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "const": "core-gdd/1.1"},
        "title": {"type": "string", "minLength": 1},
        "background": {"type": "string", "minLength": 1},
        "art_style": {"type": "string", "minLength": 1},
        "themes": {"type": "array", "items": {"type": "string"}},
        "world_rules": {"type": "array", "items": {"type": "string"}},
        "immutable_facts": {"type": "array", "items": {"type": "string"}},
        "initial_conflict": {"type": "string", "minLength": 1},
        "global_goal": {
            "type": "object",
            "required": [
                "objective", "dramatic_question", "terminal_conditions",
                "forbidden_outcomes"
            ],
            "additionalProperties": False,
            "properties": {
                "objective": {"type": "string", "minLength": 1},
                "dramatic_question": {"type": "string", "minLength": 1},
                "terminal_conditions": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1}
                },
                "forbidden_outcomes": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1}
                }
            }
        },
        "ending_conditions": {"type": "array", "items": {"type": "string"}},
        "characters": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "id", "name", "gender", "is_protagonist", "personality",
                    "appearance", "background", "desire", "fear", "secret"
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
                    "speech_style": {"type": "string"}
                }
            }
        },
        "scenes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "name", "description"],
                "additionalProperties": True,
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "name": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1}
                }
            }
        },
        "initial_world_state": {"type": "object"},
        "initial_agenda": {
            "type": "object",
            "required": [
                "open_questions", "unresolved_conflicts", "foreshadowing",
                "character_arcs"
            ],
            "additionalProperties": True,
            "properties": {
                "open_questions": {"type": "array", "items": {"type": "string"}},
                "unresolved_conflicts": {"type": "array", "items": {"type": "string"}},
                "foreshadowing": {"type": "array", "items": {"type": "string"}},
                "character_arcs": {"type": "object"}
            }
        }
    }
}


DISCOURSE_TRANSITION_SCHEMA = {
    "type": "object",
    "required": [
        "relation_to_previous", "source_scene", "source_speaker",
        "source_anchor", "bridge_requirement"
    ],
    "additionalProperties": False,
    "properties": {
        "relation_to_previous": {
            "type": "string",
            "enum": [
                "root", "acknowledgement", "answer", "continuation",
                "elaboration", "explanation", "result", "correction",
                "contrast", "topic_shift"
            ]
        },
        "source_scene": {"type": "string"},
        "source_speaker": {"type": "string"},
        "source_anchor": {"type": "string"},
        "bridge_requirement": {"type": "string", "minLength": 1}
    }
}


NODE_GOAL_SCHEMA = {
    "type": "object",
    "required": [
        "goal", "dramatic_question", "contributes_to_global_goal",
        "completion_conditions", "forbidden_outcomes", "narrative_phase",
        "transition_contract"
    ],
    "additionalProperties": False,
    "properties": {
        "goal": {"type": "string", "minLength": 1},
        "dramatic_question": {"type": "string", "minLength": 1},
        "contributes_to_global_goal": {"type": "string", "minLength": 1},
        "completion_conditions": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1}
        },
        "forbidden_outcomes": {
            "type": "array",
            "items": {"type": "string", "minLength": 1}
        },
        "narrative_phase": {
            "type": "string",
            "enum": ["setup", "escalation", "confrontation", "resolution"]
        },
        "transition_contract": DISCOURSE_TRANSITION_SCHEMA
    }
}


PRODUCER_NODE_REVIEW_SCHEMA = {
    "type": "object",
    "required": [
        "decision", "feedback", "goal_completed", "summary",
        "state_updates", "agenda", "terminal_condition_checks", "closure_check",
        "continuity_check"
    ],
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["PASS", "REVISE"]},
        "feedback": {"type": "array", "items": {"type": "string"}},
        "goal_completed": {"type": "boolean"},
        "summary": {"type": "string"},
        "state_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "value", "evidence"],
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "value": {},
                    "evidence": {"type": "string", "minLength": 1}
                }
            }
        },
        "agenda": {"type": "object"},
        "continuity_check": {
            "type": "object",
            "required": [
                "applicable", "relation_to_previous", "source_anchor_acknowledged",
                "discourse_relation_realized", "action_continuity_preserved",
                "scene_transition_grounded", "evidence"
            ],
            "additionalProperties": False,
            "properties": {
                "applicable": {"type": "boolean"},
                "relation_to_previous": {"type": "string"},
                "source_anchor_acknowledged": {"type": "boolean"},
                "discourse_relation_realized": {"type": "boolean"},
                "action_continuity_preserved": {"type": "boolean"},
                "scene_transition_grounded": {"type": "boolean"},
                "evidence": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1}
                }
            }
        },
        "terminal_condition_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["condition", "satisfied", "evidence"],
                "additionalProperties": False,
                "properties": {
                    "condition": {"type": "string", "minLength": 1},
                    "satisfied": {"type": "boolean"},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1}
                    }
                }
            }
        },
        "closure_check": {
            "type": "object",
            "required": [
                "conflict_resolved", "consequences_shown",
                "character_arcs_paid_off", "new_equilibrium_established",
                "finality_signal_present", "evidence", "final_beat"
            ],
            "additionalProperties": False,
            "properties": {
                "conflict_resolved": {"type": "boolean"},
                "consequences_shown": {"type": "boolean"},
                "character_arcs_paid_off": {"type": "boolean"},
                "new_equilibrium_established": {"type": "boolean"},
                "finality_signal_present": {"type": "boolean"},
                "final_beat": {"type": "string"},
                "evidence": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1}
                }
            }
        }
    }
}


SCENE_CONTRACT_SCHEMA = {
    "type": "object",
    "required": [
        "goal", "dramatic_question", "active_cast", "location",
        "required_outcomes", "forbidden_outcomes"
    ],
    "additionalProperties": False,
    "properties": {
        "goal": {"type": "string", "minLength": 1},
        "dramatic_question": {"type": "string", "minLength": 1},
        "active_cast": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1}
        },
        "location": {"type": "string", "minLength": 1},
        "required_outcomes": {"type": "array", "items": {"type": "string"}},
        "forbidden_outcomes": {"type": "array", "items": {"type": "string"}}
    }
}


ROLLING_PLAN_SCHEMA = {
    "type": "object",
    "required": ["scene_summary", "world_state", "agenda", "next_scene"],
    "additionalProperties": False,
    "properties": {
        "scene_summary": {"type": "string", "minLength": 1},
        "world_state": {"type": "object"},
        "agenda": {"type": "object"},
        "next_scene": SCENE_CONTRACT_SCHEMA
    }
}

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


ACTOR_PERFORMANCE_SCHEMA = {
    "type": "object",
    "required": ["thought", "action", "dialogue", "image"],
    "additionalProperties": False,
    "properties": {
        "thought": {
            "type": "string"
        },
        "action": {
            "type": "string"
        },
        "dialogue": {
            "type": "string"
        },
        "image": {
            "type": "string"
        }
    }
}


CG_SCRIPT_PACKAGE_SCHEMA = {
    "type": "object",
    "required": ["script", "cgs"],
    "additionalProperties": False,
    "properties": {
        "script": {"type": "string", "minLength": 1},
        "cgs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "node_id", "characters", "description"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "node_id": {"type": "string", "minLength": 1},
                    "characters": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "uniqueItems": True,
                    },
                    "description": {"type": "string", "minLength": 80},
                },
            },
        },
    },
}
