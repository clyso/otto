# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations
from dataclasses import dataclass
import base64
import binascii
import json
import os
import threading
from typing import Optional, Dict, Any, Callable
import logging
import time
import requests
from clyso.ceph.ai.common import jsoncmd
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import queue
import subprocess
from .command_registry import CommandRegistry, CommandType

WEBHOOK_CONFIG_FILE = "/etc/ceph/copilot-webhook"
DEFAULT_HEARTBEAT_INTERVAL = 1
DEFAULT_PBK_ITERATIONS = 100000


class CommandError(Exception):
    """Exception raised for errors during command execution."""

    pass


class CommandNotFoundError(CommandError):
    """Exception raised when a command is not found in the registry."""

    pass


class CommandHandlerNotFoundError(CommandError):
    """Exception raised when no handler is registered for a command"""

    def __init__(self, command_name: str):
        self.command_name = command_name
        super().__init__(f"No handler registered for command: {command_name}")


class CommandResultFormatError(CommandError):
    """Exception raised when a command result cannot be properly formatted"""

    def __init__(
        self, command_name: str, message: str, cause: Optional[Exception] = None
    ):
        self.command_name = command_name
        self.cause = cause
        super().__init__(
            f"Failed to format result for command '{command_name}': {message}"
        )


class CommandResponseError(Exception):
    """Exception raised when there is an error sending a command response"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        command_uuid: Optional[str] = None,
    ):
        self.status_code = status_code
        self.command_uuid = command_uuid
        super().__init__(message)


class DecryptionError(Exception):
    """Exception raised when payload decryption fails"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.original_error = original_error
        super().__init__(message)


class WebhookRegistrationError(Exception):
    """Exception raised when webhook registration fails"""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        self.cause = cause
        super().__init__(message)


class HeartbeatError(Exception):
    """Exception raised when there is an error with the heartbeat process"""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        self.cause = cause
        super().__init__(message)


class Command:
    """Class for handling commands and their execution."""

    def __init__(self, name: str, uuid: str, args: Optional[Dict[str, Any]] = None):
        self.name = name
        self.uuid = uuid
        self.args = args
        self.logger = logging.getLogger(__name__)
        self.registry = CommandRegistry()

    def execute(self) -> Any:
        """
        Execute the command and return the raw result.

        Returns:
            Any: Raw result from command execution

        Raises:
            CommandNotFoundError: If the command is not found in the registry
            CommandHandlerNotFoundError: If no handler is registered for the command
            CommandResultFormatError: If the result cannot be formatted
            CommandError: If there is an error executing the command
        """
        # Validate the command first
        if not self.registry.is_command_registered(self.name):
            raise CommandNotFoundError(f"Command not found: {self.name}")

        try:
            # Get command info from registry
            command_info = self.registry.get_command(self.name)

            # Check if a handler is registered
            if not command_info["handler"]:
                raise CommandHandlerNotFoundError(self.name)

            # Execute the command using its handler
            if command_info["type"] == CommandType.CEPH:
                # For Ceph commands, pass the command value to the handler
                return command_info["handler"](command_info["value"])
            else:
                # For Copilot commands, pass the args to the handler
                return self._execute_copilot_command(
                    command_info["handler"], command_info["default_args"]
                )
        except (CommandHandlerNotFoundError, CommandResultFormatError):
            raise
        except Exception as e:
            raise CommandError(f"Command execution failed: {e}")

    def _execute_copilot_command(
        self, handler: Callable[..., Any], default_args: Dict[str, Any]
    ) -> str:
        """
        Execute an internal Copilot command using its registered handler.

        Args:
            handler: The handler function for the command
            default_args: Default arguments for the command

        Returns:
            str: The command output

        Raises:
            CommandResultFormatError: If the result cannot be formatted
        """
        # Prepare arguments for the handler
        merged_args = {**default_args, **(self.args or {})}

        # Create a mock args object with the provided arguments
        class MockArgs:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        args = MockArgs(**merged_args)

        # Execute the handler
        result = handler(args)

        # Format the result
        try:
            if isinstance(result, str):
                return result
            else:
                return json.dumps(result)
        except (TypeError, OverflowError, ValueError) as e:
            raise CommandResultFormatError(
                self.name, "Result cannot be converted to JSON", e
            )


@dataclass
class CopilotSecret:
    """Handles the secret for webhook"""

    url: str
    cluster_id: str
    password: str

    @classmethod
    def from_base64(cls, secret: str) -> CopilotSecret:
        """Decode base64 secret into CopilotSecret object"""
        try:
            decoded = base64.b64decode(secret).decode("utf-8")
        except binascii.Error as e:
            raise ValueError(f"failed to decode secret: {e}")

        try:
            data = json.loads(decoded)
            return cls(
                url=data["url"], cluster_id=data["clusterId"], password=data["password"]
            )
        except Exception as e:
            raise ValueError(f"failed to parse secret json: {e}")

    @classmethod
    def from_file(cls, file_path: str = WEBHOOK_CONFIG_FILE) -> CopilotSecret:
        """Read secret from config file"""
        try:
            with open(file_path, "r") as f:
                secret = f.read().strip()
            return cls.from_base64(secret)
        except Exception as e:
            raise ValueError(f"invalid secret format: {e}")


class PayloadCrypto:
    """Handles encryption and decription of payloads using AES-GCM"""

    def __init__(self, password: str):
        self.password = password
        self.pbk_iterations = DEFAULT_PBK_ITERATIONS

    def encrypt(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Encrypt payload using AES-GCM"""
        # Generate a random 32-byte salt
        salt = os.urandom(32)

        # Derive key from password using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.pbk_iterations,
        )
        key = kdf.derive(self.password.encode())

        # Generate a random nonce
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)

        # Encrypt the data
        data_bytes = json.dumps(data).encode()
        ciphertext = aesgcm.encrypt(nonce, data_bytes, None)

        return {
            "encryptedData": base64.b64encode(ciphertext).decode("utf-8"),
            "nonce": base64.b64encode(nonce).decode("utf-8"),
            "salt": base64.b64encode(salt).decode("utf-8"),
        }

    def decrypt(self, encrypted_payload: Dict[str, str]) -> Dict[str, Any]:
        """Decrypt payload using AES-GCM"""

        # Check for required fields
        for field in ["encryptedData", "nonce", "salt"]:
            if field not in encrypted_payload:
                raise DecryptionError(
                    f"Missing required field in encrypted payload: '{field}'"
                )

        # Decode base64 values
        try:
            ciphertext = base64.b64decode(encrypted_payload["encryptedData"])
        except binascii.Error as e:
            raise DecryptionError(f"Invalid base64 encoding in 'encryptedData': {e}", e)

        try:
            nonce = base64.b64decode(encrypted_payload["nonce"])
        except binascii.Error as e:
            raise DecryptionError(f"Invalid base64 encoding in 'nonce': {e}", e)

        try:
            salt = base64.b64decode(encrypted_payload["salt"])
        except binascii.Error as e:
            raise DecryptionError(f"Invalid base64 encoding in 'salt': {e}", e)

        # Derive key from password
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.pbk_iterations,
        )
        key = kdf.derive(self.password.encode())

        # Decrypt the data
        try:
            aesgcm = AESGCM(key)
            decrypted_data = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            raise DecryptionError(f"AES-GCM decryption failed: {e}", e)

        # Parse the JSON result
        try:
            return json.loads(decrypted_data.decode())
        except UnicodeDecodeError as e:
            raise DecryptionError(f"Decrypted data is not valid UTF-8: {e}", e)
        except json.JSONDecodeError as e:
            raise DecryptionError(f"Decrypted data is not valid JSON: {e}", e)
        except Exception as e:
            raise DecryptionError(f"Failed to process decrypted data: {e}", e)


class CommandExecutor:
    """Handles asynchronus command execution"""

    def __init__(self, secret: CopilotSecret, logger: logging.Logger):
        self.secret = secret
        self.logger = logger
        self.command_queue: queue.Queue[Command] = queue.Queue()
        self.running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.crypto = PayloadCrypto(secret.password)

    def start(self):
        """Start the command executor"""
        if self.running:
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def stop(self):
        """Stop the command executor"""
        if not self.running:
            return

        self.running = False

        if self.worker_thread:
            self.worker_thread.join()
            self.worker_thread = None

        # Clear the queue
        unfinished_tasks = self.command_queue.unfinished_tasks
        if unfinished_tasks > 0:
            self.logger.info(f"Discarding {unfinished_tasks} unprocessed commands")

            # Empty the queue
            with self.command_queue.mutex:
                self.command_queue.queue.clear()
                self.command_queue.unfinished_tasks = 0
                self.command_queue.all_tasks_done.notify_all()

    def add_command(self, command: Command):
        """Add a command to the execution queue"""
        if not command.registry.is_command_registered(command.name):
            raise ValueError(
                f"command not allowed: {command.name} (type: {command.registry.get_command(command.name)['type'].value})"
            )
        self.command_queue.put(command)

    def _send_command_response(self, response: Dict[str, Any]) -> None:
        """Send the encrypted result of command execution to the webhook

        Raises:
            CommandResponseError: If server returns non-200 status code or other response-related errors
            KeyError: If required fields are missing in the response
            Exception: For other unexpected errors
        """
        command_uuid = response.get("uuid", "unknown")

        # Encrypt the response
        try:
            encrypted_response = self.crypto.encrypt(response)
        except Exception as e:
            raise CommandResponseError(
                f"Failed to encrypt response: {e}", command_uuid=command_uuid
            ) from e

        # Send the HTTP request and check the response
        try:
            api_response = requests.post(
                f"{self.secret.url}/webhook/{self.secret.cluster_id}/command/{command_uuid}",
                json=encrypted_response,
                timeout=10,
            )
        except requests.RequestException as e:
            raise CommandResponseError(
                f"HTTP request failed: {e}", command_uuid=command_uuid
            ) from e

        # Check the response status
        if api_response.status_code != 200:
            raise CommandResponseError(
                f"Server returned status code {api_response.status_code}: {api_response.text}",
                status_code=api_response.status_code,
                command_uuid=command_uuid,
            )

    def _worker_loop(self):
        """Thread for execution of commands from the command queue"""
        while self.running:
            command = None
            response = None

            # Get command from queue with timeout
            try:
                command = self.command_queue.get(timeout=1)
            except queue.Empty:
                continue

            # Execute command
            try:
                self.logger.info(f"Executing command with uuid: {command.uuid}")

                # Execute command
                result = command.execute()

                # Prepare success response
                response = {"uuid": command.uuid, "status": "SUCCESS", "result": result}
            except CommandHandlerNotFoundError as e:
                # Handle missing handler errors
                self.logger.error(
                    f"No handler found for command {command.name} ({command.uuid}): {e}"
                )
                response = {
                    "uuid": command.uuid,
                    "status": "ERROR",
                    "error": f"Command handler not found: {e}",
                }
            except CommandResultFormatError as e:
                # Handle result formatting errors
                self.logger.error(
                    f"Result format error for command {command.name} ({command.uuid}): {e}"
                )
                response = {
                    "uuid": command.uuid,
                    "status": "ERROR",
                    "error": f"Failed to format command result: {e}",
                }
            except ValueError as e:
                # Handle validation errors
                self.logger.error(
                    f"Value error during execution of {command.name} ({command.uuid}): {e}"
                )
                response = {"uuid": command.uuid, "status": "ERROR", "error": str(e)}
            except Exception as e:
                # Handle unexpected execution errors
                self.logger.error(
                    f"Unexpected error during execution of {command.name} ({command.uuid}): {e}"
                )
                response = {
                    "uuid": command.uuid,
                    "status": "ERROR",
                    "error": f"Unexpected error: {e}",
                }

            # Send response if we have one
            if response:
                try:
                    self._send_command_response(response)
                except CommandResponseError as e:
                    if e.command_uuid:
                        self.logger.error(
                            f"Error sending response for command {e.command_uuid}: {e}"
                        )
                    else:
                        self.logger.error(f"Error sending command response: {e}")
                except json.JSONDecodeError as e:
                    self.logger.error(
                        f"JSON decode error for response of command {command.uuid}: {e}"
                    )
                except KeyError as e:
                    self.logger.error(
                        f"Key error in command worker - missing field: {e}"
                    )
                except Exception as e:
                    self.logger.error(f"Unexpected error sending response: {e}")

            # mark task as completed
            self.command_queue.task_done()


class CopilotDaemon:
    def __init__(self, secret: CopilotSecret):
        self.secret = secret
        self.heartbeat_interval = DEFAULT_HEARTBEAT_INTERVAL
        self.running = False
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.logger = logging.getLogger("CopilotDaemon")
        self.command_executor = CommandExecutor(secret, self.logger)
        self.crypto = PayloadCrypto(secret.password)

    def _get_ceph_fsid(self) -> str:
        """Get ceph FSID"""
        try:
            result = jsoncmd("ceph fsid --format=json")
            return result["fsid"]
        except KeyError as e:
            self.logger.error(f"Missing 'fsid' key in Ceph command result: {e}")
            raise ValueError("Missing fsid in Ceph response") from e
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON from Ceph fsid command: {e}")
            raise ValueError("Invalid JSON response from Ceph") from e
        except subprocess.SubprocessError as e:
            self.logger.error(f"Failed to execute Ceph fsid command: {e}")
            raise ValueError("Failed to execute Ceph command") from e

    def _get_ceph_health(self) -> str:
        """Get Ceph cluster health status"""
        try:
            result = jsoncmd("ceph health --format=json")
            return result["status"]
        except KeyError as e:
            self.logger.error(f"Missing 'status' key in Ceph health result: {e}")
            raise ValueError("Missing status in Ceph health response") from e
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON from Ceph health command: {e}")
            raise ValueError("Invalid JSON response from Ceph") from e
        except subprocess.SubprocessError as e:
            self.logger.error(f"Failed to execute Ceph health command: {e}")
            raise ValueError("Failed to execute Ceph command") from e

    def register_webhook(self) -> None:
        """Register webhook with the backend

        Raises:
            WebhookRegistrationError: If registration fails for any reason
        """
        # Get FSID and health status
        try:
            fsid = self._get_ceph_fsid()
        except ValueError as e:
            self.logger.error(f"Failed to get Ceph FSID: {e}")
            raise WebhookRegistrationError("Failed to get Ceph FSID", e) from e

        try:
            health = self._get_ceph_health()
        except ValueError as e:
            self.logger.error(f"Failed to get Ceph health: {e}")
            raise WebhookRegistrationError("Failed to get Ceph health", e) from e

        # Prepare and encrypt payload
        payload = {"health": health, "fsid": fsid, "clusterId": self.secret.cluster_id}

        try:
            encrypted_payload = self.crypto.encrypt(payload)
        except (TypeError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to encrypt webhook payload: {e}")
            raise WebhookRegistrationError(
                "Failed to encrypt webhook payload", e
            ) from e
        except Exception as e:
            self.logger.error(f"Unexpected error during payload encryption: {e}")
            raise WebhookRegistrationError(
                "Unexpected error during payload encryption", e
            ) from e

        # Send webhook registration request
        try:
            response = requests.post(
                f"{self.secret.url}/webhook/{self.secret.cluster_id}/register",
                json=encrypted_payload,
                timeout=10,
            )
        except requests.RequestException as e:
            self.logger.error(f"HTTP error during webhook registration: {e}")
            raise WebhookRegistrationError(
                "HTTP error during webhook registration", e
            ) from e

        # Process response
        if response.status_code != 200:
            error_msg = f"Failed to register webhook: {response.text}"
            self.logger.error(error_msg)
            raise WebhookRegistrationError(error_msg)

        # Decrypt response
        try:
            decrypted_data = self.crypto.decrypt(response.json())
            self.heartbeat_interval = decrypted_data.get("heartbeatIntervalSeconds", 1)
        except (KeyError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to process webhook registration response: {e}")
            raise WebhookRegistrationError(
                "Failed to process webhook registration response", e
            ) from e
        except DecryptionError as e:
            self.logger.error(f"Failed to decrypt response: {e}")
            raise WebhookRegistrationError("Failed to decrypt response", e) from e

    def _heartbeat_loop(self):
        """Thread for sending heartbeats"""
        while self.running:
            # Get Ceph health status
            try:
                health = self._get_ceph_health()
            except ValueError as e:
                self.logger.error(f"Failed to get Ceph health for heartbeat: {e}")
                time.sleep(self.heartbeat_interval)
                continue

            # Send heartbeat request
            try:
                response = requests.get(
                    f"{self.secret.url}/webhook/{self.secret.cluster_id}/heartbeat",
                    params={"status": health},
                    timeout=10,
                )
            except requests.RequestException as e:
                self.logger.error(f"HTTP error sending heartbeat: {e}")
                time.sleep(self.heartbeat_interval)
                continue

            # Check response status
            if response.status_code != 200:
                self.logger.warning(
                    f"Heartbeat failed with status {response.status_code}: {response.text}"
                )
                time.sleep(self.heartbeat_interval)
                continue

            # Decrypt the response
            try:
                decrypted_data = self.crypto.decrypt(response.json())
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON from heartbeat response: {e}")
                time.sleep(self.heartbeat_interval)
                continue
            except DecryptionError as e:
                self.logger.error(f"Failed to decrypt heartbeat response: {e}")
                time.sleep(self.heartbeat_interval)
                continue
            except Exception as e:
                self.logger.error(
                    f"Unexpected error processing heartbeat response: {e}"
                )
                time.sleep(self.heartbeat_interval)
                continue

            # Process command if present
            if "command" in decrypted_data and decrypted_data["command"] is not None:
                cmd_data = decrypted_data["command"]
                
                # Validate required fields and their types
                if not isinstance(cmd_data.get("name"), str):
                    self.logger.error("Command name must be a string")
                    return
                if not isinstance(cmd_data.get("uuid"), str):
                    self.logger.error("Command UUID must be a string")
                    return
                
                # Args is optional but must be a valid json string
                args = {}
                if "args" in cmd_data and cmd_data["args"] is not None:
                    if not isinstance(cmd_data["args"], str):
                        self.logger.error("Command args must be a JSON string")
                        return
                    try:
                        args = json.loads(cmd_data["args"])
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Invalid JSON in command args: {e}")
                        return
                
                command = Command(
                    name=cmd_data["name"],
                    uuid=cmd_data["uuid"],
                    args=args,
                )
                self.command_executor.add_command(command)

            # Update heartbeat interval if provided
            try:
                if "heartbeatIntervalSeconds" in decrypted_data:
                    self.heartbeat_interval = decrypted_data["heartbeatIntervalSeconds"]
            except Exception as e:
                self.logger.error(f"Error updating heartbeat interval: {e}")

            # Sleep until next heartbeat
            time.sleep(self.heartbeat_interval)

    def start(self):
        """Start the daemon

        Raises:
            WebhookRegistrationError: If webhook registration fails
        """
        if self.running:
            return

        # Register webhook (will raise WebhookRegistrationError if it fails)
        self.register_webhook()

        self.running = True

        # Start the command executor
        self.command_executor.start()

        # Start the heartbeat thread
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()

        self.logger.info("Copilot daemon started successfully")

    def stop(self):
        """Stop the daemon"""
        if not self.running:
            return

        self.running = False
        self.command_executor.stop()

        if self.heartbeat_thread:
            self.heartbeat_thread.join()
            self.heartbeat_thread = None

        self.logger.info("Copilot daemon stopped")
