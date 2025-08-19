from typing import Dict, Any, Callable, Optional
from enum import Enum
from clyso.ceph.ai.common import jsoncmd


class CommandType(str, Enum):
    CEPH = "ceph"  # Direct Ceph commands
    COPILOT = "copilot"  # Internal copilot commands


class CommandRegistry:
    """Singleton class to maintain the command registry."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CommandRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._commands: Dict[str, Dict[str, Any]] = {}
        self._initialized = True

        # Register default commands
        self._register_default_commands()

    def _register_default_commands(self):
        """Register the default set of commands"""
        default_commands = {
            # Ceph commands
            "health": {"type": CommandType.CEPH, "value": "ceph health --format=json"},
            "status": {"type": CommandType.CEPH, "value": "ceph status --format=json"},
            "fsid": {"type": CommandType.CEPH, "value": "ceph fsid --format=json"},
            "report": {"type": CommandType.CEPH, "value": "ceph report --format=json"},
            "osd_tree": {
                "type": CommandType.CEPH,
                "value": "ceph osd tree --format=json",
            },
            "pg_stat": {
                "type": CommandType.CEPH,
                "value": "ceph pg stat --format=json",
            },
            "mon_stat": {
                "type": CommandType.CEPH,
                "value": "ceph mon stat --format=json",
            },
            "osd_stat": {
                "type": CommandType.CEPH,
                "value": "ceph osd stat --format=json",
            },
            "osd_pool_ls": {
                "type": CommandType.CEPH,
                "value": "ceph osd pool ls --format=json",
            },
            "df": {"type": CommandType.CEPH, "value": "ceph df --format=json"},
        }

        for name, command in default_commands.items():
            # For Ceph commands, use jsoncmd as the handler
            self.register(
                name=name, type=command["type"], value=command["value"], handler=jsoncmd
            )

    def register(
        self,
        name: str,
        type: CommandType,
        value: str,
        handler: Optional[Callable[..., Any]] = None,
        default_args: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a new command in the registry.

        Args:
            name: The name of the command
            type: The type of command (CEPH or COPILOT)
            value: The command value or template
            handler: The handler function for the command
            default_args: Optional default arguments for the command
        """
        self._commands[name] = {
            "type": type,
            "value": value,
            "handler": handler,
            "default_args": default_args or {},
        }

    def get_command(self, name: str) -> Dict[str, Any]:
        """
        Get a command by name.

        Args:
            name: The name of the command to retrieve

        Returns:
            Dict containing the command name, type, value, handler, and default args

        Raises:
            KeyError: If the command is not found
        """
        if name not in self._commands:
            raise KeyError(f"Command not found: {name}")
        return self._commands[name]

    def get_all_commands(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all registered commands.

        Returns:
            Dict of all registered commands
        """
        return self._commands.copy()

    def is_command_registered(self, name: str) -> bool:
        """
        Check if a command is registered.

        Args:
            name: The name of the command to check

        Returns:
            True if the command is registered, False otherwise
        """
        return name in self._commands

    def unregister(self, name: str) -> None:
        """
        Unregister a command.

        Args:
            name: The name of the command to unregister

        Raises:
            KeyError: If the command is not found
        """
        if name not in self._commands:
            raise KeyError(f"Command not found: {name}")
        del self._commands[name]
