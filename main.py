from fastmcp import FastMCP

mcp = FastMCP("openroad-mcp")

@mcp.tool()
def greet(name: str = "World") -> str:
    return f"Hello, {name}!"

@mcp.prompt()
def prompt() -> str:
    return "What is your name?"

@mcp.resource(uri="resource://test")
def resource() -> str:
    return "This is a resource."

if __name__ == "__main__":
    mcp.run(transport="stdio")
