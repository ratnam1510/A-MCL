import re
import sys

def patch_file(filepath, pattern_str):
    with open(filepath, 'r') as f:
        code = f.read()

    # Add Context import if missing
    if 'Context' not in code:
        code = code.replace(
            'from mcp.server.fastmcp import FastMCP',
            'from mcp.server.fastmcp import FastMCP, Context'
        )

    pattern = re.compile(pattern_str)

    def replacement(match):
        name = match.group(1)
        args = match.group(2)
        # add ctx argument
        if not args.strip():
            new_args = "ctx: Context = None"
        else:
            new_args = args + ", ctx: Context = None"
        
        return f'async def {name}({new_args}) -> str:\n        await ctx_mgr.ensure_project(ctx)'

    code = pattern.sub(replacement, code)

    with open(filepath, 'w') as f:
        f.write(code)

patch_file('src/amcl/mcp/resources.py', r'def ([a-z_]+)\(([^)]*)\) -> str:')
patch_file('src/amcl/mcp/prompts.py', r'def ([a-z_]+)\(([^)]*)\) -> str:')

