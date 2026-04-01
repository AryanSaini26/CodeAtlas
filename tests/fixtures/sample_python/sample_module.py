"""Sample Python module for testing the CodeAtlas parser."""

import os
import sys
from typing import Optional
from pathlib import Path
from collections import defaultdict

MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30


def standalone_function(x: int, y: int) -> int:
    """Add two integers."""
    return x + y


def function_with_calls(items: list[str]) -> list[str]:
    """Process a list of items."""
    result = sorted(items)
    return list(set(result))


class BaseModel:
    """A simple base model class."""

    def __init__(self, name: str) -> None:
        self.name = name

    def get_name(self) -> str:
        """Return the model name."""
        return self.name

    def __repr__(self) -> str:
        return f"BaseModel(name={self.name!r})"


class ChildModel(BaseModel):
    """Inherits from BaseModel."""

    def __init__(self, name: str, value: int) -> None:
        super().__init__(name)
        self.value = value

    def compute(self) -> int:
        """Compute something."""
        return self.value * 2


def decorator_factory(flag: bool):
    """A decorator factory."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


@decorator_factory(flag=True)
def decorated_function(x: int) -> int:
    """A decorated function."""
    return x + 1


class ServiceClass:
    """A class with multiple methods and a nested function."""

    CLASS_CONSTANT = "service"

    def process(self, data: dict) -> Optional[str]:
        """Process data and return a result."""
        def inner_helper(item):
            return str(item)

        result = inner_helper(data)
        return result

    @staticmethod
    def static_method() -> str:
        return "static"

    @classmethod
    def class_method(cls) -> str:
        return cls.CLASS_CONSTANT
