"""src/docs/schema_builder.py — OpenAPI 스키마 빌더."""
import logging

logger = logging.getLogger(__name__)

_TYPE_MAP = {
    'str': 'string',
    'int': 'integer',
    'float': 'number',
    'bool': 'boolean',
    'list': 'array',
    'dict': 'object',
}


class SchemaBuilder:
    """OpenAPI 3.0 스키마 빌더."""

    def build_parameter_schema(
        self, name: str, type_: str = 'string', required: bool = False, description: str = ''
    ) -> dict:
        return {
            'name': name,
            'in': 'query',
            'required': required,
            'description': description,
            'schema': {'type': _TYPE_MAP.get(type_, type_)},
        }

    def build_response_schema(
        self, status_code: int, description: str = '', example: dict = None
    ) -> dict:
        schema = {'description': description}
        if example:
            schema['content'] = {
                'application/json': {
                    'schema': {'type': 'object'},
                    'example': example,
                }
            }
        return {str(status_code): schema}

    def build_request_schema(self, properties: dict) -> dict:
        return {
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            k: {'type': _TYPE_MAP.get(v, v)} for k, v in properties.items()
                        },
                    }
                }
            }
        }
