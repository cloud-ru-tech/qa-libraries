# SSH client

[![PyPI](https://img.shields.io/pypi/v/cloudru-qa-ssh-client)](https://pypi.org/project/cloudru-qa-ssh-client/)
[![Python](https://img.shields.io/pypi/pyversions/cloudru-qa-ssh-client)](https://pypi.org/project/cloudru-qa-ssh-client/)
[![License](https://img.shields.io/pypi/l/cloudru-qa-ssh-client)](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)

English | [Русский](README.ru.md)

A simple SSH client library for automated tests: synchronous and asynchronous clients with
constructor options, command decorators, and logging.

## Installation

Requires Python 3.13 or later.

```shell
pip install cloudru-qa-ssh-client
```

For structured logging with structlog, install the `structlog` extra:

```shell
pip install "cloudru-qa-ssh-client[structlog]"
```

Import the library as the module `ssh_client`.

## Skills for AI agents

This library does not have its own skill yet. If your project uses other
libraries from this suite with [skills for AI agents](https://github.com/cloud-ru-tech/qa-libraries#skills-for-ai-agents),
select and enable them from your project root (requires [`uv`](https://docs.astral.sh/uv/)):

```shell
uvx library-skills
```

For Claude Code, add `--claude`.

## Main features

1. Connect to remote hosts using a password or a key
2. Run commands as strings or lists of shell command fragments
3. Set timeouts for the client and individual requests
4. Check exit codes with `raise_for_status=True` for individual commands
5. Configure retry counts and intervals
6. Retry connection and command failures
7. Get result objects with stdout, stderr, and exit code fields
8. Log requests and responses with a supplied logger
9. Mask request and response logs using strings or regular expressions
10. Use asynchronous clients through asyncssh
11. Receive output in real time for interactive commands
12. Interrupt commands with conditional callbacks

## Usage example

### Synchronous client

```python
import logging
from ssh_client import SyncSSHClient, options

# Create a logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a client
client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    options.with_request_timeout(30),
    options.with_logger(logger),
)

# Run a command
result = client.execute(["ls", "-la"])
print(f"Exit code: {result.exit_code}")
print(f"Stdout: {result.stdout}")
print(f"Stderr: {result.stderr}")

# Close the connection
client.close()
```

### Asynchronous client

```python
import asyncio
import logging
from ssh_client import AsyncSSHClient, options


async def main():
    # Create a logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Create a client
    client = AsyncSSHClient(
        "example.com",
        22,
        options.with_private_key("user", "/path/to/private/key"),
        options.with_request_timeout(30),
        options.with_logger(logger),
    )

    # Run a command
    result = await client.execute(["ls", "-la"])
    print(f"Exit code: {result.exit_code}")
    print(f"Stdout: {result.stdout}")
    print(f"Stderr: {result.stderr}")

    # Close the connection
    await client.aclose()


# Run the asynchronous function
asyncio.run(main())
```

## Configuration

Configure the client using `ClientOption` options. Built-in options are in the `options` module.

By default, both clients verify server keys against the standard `~/.ssh/known_hosts` file.
Unknown or changed keys are rejected. To use a separate file, set
`options.with_known_hosts("/path/to/known_hosts")`; the file must contain a previously verified server key.

### Available options

* `with_request_timeout`: set the SSH request timeout
* `with_connection_timeout`: set the SSH connection timeout
* `with_password`: set the username and password for authentication
* `with_private_key`: set the username and private key path for authentication
* `with_known_hosts`: choose a trusted server keys file
* `with_logger`: set a logger for SSH requests and responses
* `with_structlogger`: set a structured logger for SSH requests and responses (requires the structlog extra)
* `retry_if_connection_fails`: retry failed connections
* `retry_if_command_fails`: retry failed commands
* `with_connect_decorators`: add custom decorators to the connection method
* `with_execute_decorators`: add custom decorators to the command execution method
* `with_live_execute_callback`: add callbacks to process stdout and stderr lines in real time

### Using with_live_execute_callback

```python
import logging
from ssh_client import SyncSSHClient, options


# Define callbacks for live output
def stdout_callback(line):
    print(f"STDOUT: {line}")


def stderr_callback(line):
    print(f"STDERR: {line}")


# Create a client with callbacks
client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    options.with_live_execute_callback(stdout_callback, stderr_callback),
)

# Run a command with live output
result = client.execute_live(["ping", "-c", "3", "google.com"])

# Callbacks print all lines in real time
print(f"Exit code: {result.exit_code}")

# Close the connection
client.close()
```

### Interrupting commands with callbacks

Interrupt a command when a condition is met. This is useful for long-running commands that should stop when particular text appears in the output.

#### Interrupting on stdout (synchronous client)

```python
import logging
from ssh_client import SyncSSHClient, options


# Define a conditional interrupt callback
def interrupt_on_keyword(line):
    """Interrupt execution if the line contains 'ERROR'."""
    print(f"Processing line: {line}")
    return "ERROR" in line


# Create a client
client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
)

try:
    # Run a command with conditional interruption
    result = client.execute_live(
        ["tail", "-f", "/var/log/application.log"], interrupt_stdout_callback=interrupt_on_keyword
    )

    print(f"Command was interrupted with exit code: {result.exit_code}")
    print("Captured output:")
    for line in result.stdout_lines:
        print(f"  {line}")
finally:
    client.close()
```

#### Interrupting on stderr (asynchronous client)

```python
import asyncio
from ssh_client import AsyncSSHClient, options


async def main():
    # Define a stderr interrupt callback
    def interrupt_on_error(line):
        """Interrupt execution if stderr contains a critical error."""
        print(f"Error detected: {line}")
        return "CRITICAL" in line or "FATAL" in line

    # Create a client
    client = AsyncSSHClient(
        "example.com",
        22,
        options.with_private_key("user", "/path/to/private/key"),
    )

    try:
        # Run a command with stderr interruption
        result = await client.execute_live(["some-long-running-command"], interrupt_stderr_callback=interrupt_on_error)

        print(f"Command was interrupted with exit code: {result.exit_code}")
        print("Captured stderr:")
        for line in result.stderr_lines:
            print(f"  {line}")
    finally:
        await client.aclose()


# Run the asynchronous function
asyncio.run(main())
```

Synchronous `execute_live` merges stdout and stderr through a terminal. Separate stderr callbacks are available on the asynchronous client.

When an interrupt callback fires, the command stops and `execute_live` returns a result with a negative exit code (-1 for the synchronous client, -2 for the asynchronous client), including all lines received before the interruption.

## Advanced features

### Temporary options with with_options

Use `with_options` to create temporary clients with additional options for a single command:

```python
import logging
from ssh_client import SyncSSHClient, options

# Create the base client
client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    options.with_request_timeout(30),
    options.with_logger(logging.getLogger(__name__)),
)

# Use with_options for a command with custom settings
result = client.with_options(
    options.with_request_timeout(60),  # Longer timeout for this command only
    options.retry_if_command_fails(
        retries_attempts_number=3, retries_interval_in_seconds=1
    ),  # Retries for this command only
).execute(["sleep", "10", "&&", "echo", "Done"])

# The base client stays unchanged
client.close()
```

### Structured logging

Install the `structlog` extra to use structured logging:

```shell
pip install "cloudru-qa-ssh-client[structlog]"
```

Structured logging example:

```python
import structlog
from ssh_client import SyncSSHClient, options

# Configure structlog
structlog.configure(
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

# Create a client with a structured logger
client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    options.with_structlogger(structlog.get_logger()),
)

# Run a command with structured logging
result = client.execute(["ls", "-la"])
print(f"Exit code: {result.exit_code}")

# Close the connection
client.close()
```

### Retries

Configure retries for both connections and command execution:

```python
from ssh_client import SyncSSHClient, options

client = SyncSSHClient(
    "unstable-server.com",
    22,
    options.with_password("user", "password"),
    # Connection retries
    options.retry_if_connection_fails(
        retries_attempts_number=5, retries_interval_in_seconds=10.0, reraise_exception=True
    ),
    # Command retries
    options.retry_if_command_fails(retries_attempts_number=3, retries_interval_in_seconds=5.0, reraise_exception=True),
)

# Run a command with retries
result = client.execute(["some-unstable-command"])

# Close the connection
client.close()
```

### Masking log data

Mask confidential data in logs:

```python
import logging
import re
from ssh_client import SyncSSHClient, options

# Configure a logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    # Mask confidential log data
    options.with_logger(
        logger,
        mask_patterns=[
            "password",  # String to replace
            "secret",  # Another string to replace
            re.compile(r"token=\w+"),  # Regular expression
        ],
    ),
)

# Run a command with confidential data
# The data is masked in logs
result = client.execute(["echo", "password=secret123", "token=abc123def456"])

# Close the connection
client.close()
```

### Custom decorators

Add custom decorators to connection and command execution methods:

```python
import time
from functools import wraps
from ssh_client import SyncSSHClient, options


# Decorator to measure execution time
def timing_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"{func.__name__} took {end_time - start_time:.2f} seconds")
        return result

    return wrapper


# Decorator to handle errors
def error_handler_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Error in {func.__name__}: {e}")
            # Retry or take another action here
            raise

    return wrapper


client = SyncSSHClient(
    "example.com",
    22,
    options.with_password("user", "password"),
    # Add connection decorators
    options.with_connect_decorators(timing_decorator, error_handler_decorator),
    # Add command execution decorators
    options.with_execute_decorators(timing_decorator),
)

# Run a command with decorators
result = client.execute(["ls", "-la"])

# Close the connection
client.close()
```

## Development

This library is developed in the [qa-libraries](https://github.com/cloud-ru-tech/qa-libraries) monorepo
alongside the other `cloudru-qa-*` libraries. You need [`uv`](https://docs.astral.sh/uv/), GNU Make
and [`checkmake`](https://github.com/checkmake/checkmake);
run the commands from the repository root:

```shell
make sync                   # dependencies for all libraries from uv.lock
make test-ssh-client        # tests for this library
make typecheck-ssh-client   # mypy for this library
make check                  # formatting, Ruff, mypy, and tests for the whole suite
```

Tests require Docker to be running: the SSH server starts in a container automatically. Server
and client keys are generated for each run and are not stored in the repository.

Tests run on Python 3.13 and 3.14. Each version uses a separate environment:
`make sync test-ssh-client PYTHON_VERSION=3.14`.

Create a release with the Git tag `ssh-client/v<version>`. The tag version must match the version
in `packages/ssh-client/pyproject.toml`.

## License

[Apache-2.0](https://github.com/cloud-ru-tech/qa-libraries/blob/master/LICENSE)
