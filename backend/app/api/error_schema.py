ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "example": "BAD_REQUEST"},
                "message": {"type": "string", "example": "Invalid GitHub URL"},
                "details": {"type": "object", "example": {}},
            },
            "required": ["code", "message", "details"],
            "example": {
                "code": "BAD_REQUEST",
                "message": "Invalid GitHub URL",
                "details": {},
            },
        }
    },
    "required": ["error"],
    "example": {
        "error": {
            "code": "BAD_REQUEST",
            "message": "Invalid GitHub URL",
            "details": {},
        }
    },
}
