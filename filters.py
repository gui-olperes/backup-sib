import re
from jinja2 import Environment

def replace_case_insensitive(value, search, replacement):
    return re.sub(search, replacement, value, flags=re.IGNORECASE)

env = Environment()
env.filters['replace_case_insensitive'] = replace_case_insensitive
