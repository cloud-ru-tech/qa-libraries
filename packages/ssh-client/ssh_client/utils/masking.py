import re
from collections.abc import Sequence


def mask_request_data(command: str, mask_patterns: Sequence[str | re.Pattern[str]]) -> str:
    """Mask sensitive data in SSH request command.

    :param command: Command to mask
    :param mask_patterns: Patterns to use for masking sensitive data
    :returns: Masked command
    """
    masked_command = command
    for pattern in mask_patterns:
        if isinstance(pattern, str):
            masked_command = masked_command.replace(pattern, "****")
        else:
            masked_command = pattern.sub("****", masked_command)
    return masked_command


def mask_response_data(
    stdout: str,
    stderr: str,
    mask_patterns: Sequence[str | re.Pattern[str]],
) -> tuple[str, str]:
    """Mask sensitive data in SSH response stdout and stderr.

    :param stdout: Standard output to mask
    :param stderr: Standard error to mask
    :param mask_patterns: Patterns to use for masking sensitive data
    :returns: Tuple of masked stdout and stderr
    """
    masked_stdout = stdout
    masked_stderr = stderr
    for pattern in mask_patterns:
        if isinstance(pattern, str):
            masked_stdout = masked_stdout.replace(pattern, "****")
            masked_stderr = masked_stderr.replace(pattern, "****")
        else:
            masked_stdout = pattern.sub("****", masked_stdout)
            masked_stderr = pattern.sub("****", masked_stderr)
    return masked_stdout, masked_stderr
