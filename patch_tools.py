import re

with open('src/amcl/mcp/tools.py', 'r') as f:
    code = f.read()

# Add Context import
code = code.replace(
    'from mcp.server.fastmcp import FastMCP',
    'from mcp.server.fastmcp import FastMCP, Context'
)

# Regex to patch tools
# Match: def function_name(args) -> str:
# Note arguments might be multiline
pattern = re.compile(r'def (context_[a-z_]+)\(([^)]*)\) -> str:')

def replacement(match):
    name = match.group(1)
    args = match.group(2)
    # add ctx argument
    if not args.strip():
        new_args = "ctx: Context"
    else:
        new_args = args + ", ctx: Context = None"
    
    return f'async def {name}({new_args}) -> str:\n        await ctx_mgr.ensure_project(ctx)'

code = pattern.sub(replacement, code)

with open('src/amcl/mcp/tools.py', 'w') as f:
    f.write(code)

