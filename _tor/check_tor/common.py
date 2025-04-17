from typing import Generator


def format_host(host: str) -> str:
    """
    Formats a host string. If the host is an IPv6 address, wraps it in square brackets.


    :param host: The host string to format.
    :return: The formatted host string.
    """
    return f"[{host}]" if ":" in host else host


def chunk_list(items: list[dict[str, any]], chunk_size: int) -> Generator[list[dict[str, any]], None, None]:
    """
    Splits a list into smaller chunks of a specified size.

    :param items: The list to be chunked.
    :param chunk_size: The size of each chunk.
    :return: A generator that yields chunks of the original list.
    """
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


def join_with_prefix(prefix: str, items: list[str]) -> str:
    """
    Joins a list of strings, prefixing each with a specified prefix.

    :param prefix: The common prefix to add to each item.
    :param items: The list of strings to join.
    :return: A single string with each item prefixed and joined by newlines.
    """
    return "\n".join(f"{prefix}{item}" for item in items)
