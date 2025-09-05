import unittest
from unittest.mock import MagicMock
from clyso.ceph.copilot.command_registry import CommandRegistry, CommandType


class TestCommandRegistry(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        CommandRegistry._instance = None
        self.registry = CommandRegistry()

    def test_singleton_pattern(self):
        """Test that CommandRegistry follows the singleton pattern."""
        # Create a second instance
        registry2 = CommandRegistry()

        # Both instances should be the same object
        self.assertIs(self.registry, registry2)

        # The _initialized flag should be True
        self.assertTrue(self.registry._initialized)

    def test_default_commands_registration(self):
        """Test that default commands are registered on initialization."""
        default_commands = [
            "health",
            "status",
            "fsid",
            "report",
            "osd_tree",
            "pg_stat",
            "mon_stat",
            "osd_stat",
            "osd_pool_ls",
            "df",
        ]

        for cmd in default_commands:
            self.assertTrue(self.registry.is_command_registered(cmd))

    def test_register_command(self):
        """Test registering a new command."""
        # Register a new command
        self.registry.register(
            name="test_cmd",
            type=CommandType.CEPH,
            value="ceph test --format=json",
            handler=lambda x: x,
        )

        # Check that the command is registered
        self.assertTrue(self.registry.is_command_registered("test_cmd"))

        # Get the command and verify its properties
        cmd = self.registry.get_command("test_cmd")
        self.assertEqual(cmd["type"], CommandType.CEPH)
        self.assertEqual(cmd["value"], "ceph test --format=json")
        self.assertIsNotNone(cmd["handler"])

    def test_register_copilot_command(self):
        """Test registering a Copilot command with default args."""

        # Define a test handler
        def test_handler(args):
            return f"Test handler with args: {args}"

        # Register a Copilot command
        self.registry.register(
            name="test_copilot",
            type=CommandType.COPILOT,
            value="test_value",
            handler=test_handler,
            default_args={"arg1": "value1"},
        )

        # Check that the command is registered
        self.assertTrue(self.registry.is_command_registered("test_copilot"))

        # Get the command and verify its properties
        cmd = self.registry.get_command("test_copilot")
        self.assertEqual(cmd["type"], CommandType.COPILOT)
        self.assertEqual(cmd["value"], "test_value")
        self.assertEqual(cmd["handler"], test_handler)
        self.assertEqual(cmd["default_args"], {"arg1": "value1"})

    def test_get_command_not_found(self):
        """Test getting a non-existent command."""
        with self.assertRaises(KeyError):
            self.registry.get_command("non_existent_command")

    def test_get_all_commands(self):
        """Test getting all registered commands."""
        all_commands = self.registry.get_all_commands()

        # Verify that it's a copy, not the original dictionary
        self.assertIsNot(all_commands, self.registry._commands)

        # Verify that it contains all the default commands
        default_commands = [
            "health",
            "status",
            "fsid",
            "report",
            "osd_tree",
            "pg_stat",
            "mon_stat",
            "osd_stat",
            "osd_pool_ls",
            "df",
        ]

        for cmd in default_commands:
            self.assertIn(cmd, all_commands)

    def test_unregister_command(self):
        """Test unregistering a command."""
        # Register a test command
        self.registry.register(
            name="test_cmd", type=CommandType.CEPH, value="ceph test --format=json"
        )

        # Unregister the command
        self.registry.unregister("test_cmd")

        # Verify that the command is no longer registered
        self.assertFalse(self.registry.is_command_registered("test_cmd"))

    def test_unregister_non_existent_command(self):
        """Test unregistering a non-existent command."""
        with self.assertRaises(KeyError):
            self.registry.unregister("non_existent_command")

    def test_is_command_registered(self):
        """Test checking if a command is registered."""
        # Check for a default command
        self.assertTrue(self.registry.is_command_registered("health"))

        # Check for a non-existent command
        self.assertFalse(self.registry.is_command_registered("non_existent_command"))

    def test_command_execution_with_mock(self):
        """Test command execution with a mocked handler."""
        # Create a mock handler
        mock_handler = MagicMock(return_value="mocked_result")

        # Register a command with the mock handler
        self.registry.register(
            name="mock_cmd",
            type=CommandType.COPILOT,
            value="mock_value",
            handler=mock_handler,
            default_args={"arg1": "value1"},
        )

        # Get the command
        cmd = self.registry.get_command("mock_cmd")

        # Execute the handler
        result = cmd["handler"](cmd["default_args"])

        # Verify that the handler was called with the default args
        mock_handler.assert_called_once_with({"arg1": "value1"})

        # Verify the result
        self.assertEqual(result, "mocked_result")


if __name__ == "__main__":
    unittest.main()
