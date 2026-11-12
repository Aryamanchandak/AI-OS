from tool_registry import register
from .logic import vector_db_search, vector_db_get

for _fn in (vector_db_search, vector_db_get):
    register(group="vector_db")(_fn)
