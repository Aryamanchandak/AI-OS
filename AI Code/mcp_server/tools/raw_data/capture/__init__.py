from tool_registry import register
from .logic import capture_raw_data, raw_data_status

for _fn in (capture_raw_data, raw_data_status):
    register(group="raw_data")(_fn)
