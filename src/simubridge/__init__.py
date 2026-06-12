"""SimuBridge MCP Server — give AI assistants direct access to MATLAB Simulink."""

from simubridge.app import mcp

# Register all MCP tools (decorators fire on import)
import simubridge.tools.model_management  # noqa: F401
import simubridge.tools.inspection        # noqa: F401
import simubridge.tools.modification      # noqa: F401
import simubridge.tools.simulation        # noqa: F401
import simubridge.tools.connection        # noqa: F401
import simubridge.tools.subsystem         # noqa: F401


def main():
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
