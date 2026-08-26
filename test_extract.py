
from backend.corvus.llm.ollama import _extract_text_tool_calls, _is_any_tool_call
content = '{\"name\": \"system_status\", \"arguments\": {}}'
valid_names = {'system_status'}
print('text_calls:', _extract_text_tool_calls(content, valid_names))
print('is_any_tool_call:', _is_any_tool_call(content))

