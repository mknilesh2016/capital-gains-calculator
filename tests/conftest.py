"""
Pytest configuration and shared fixtures.
"""

import sys
import os
from datetime import datetime

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def sample_sale_date():
    """Common sale date for tests."""
    return datetime(2025, 4, 15)


@pytest.fixture
def sample_acquisition_date():
    """Common acquisition date for tests."""
    return datetime(2023, 1, 15)


@pytest.fixture
def sample_sbi_rates():
    """Sample SBI rates for testing."""
    return {
        "2023-01-15": 82.0,
        "2024-04-15": 83.5,
        "2025-04-15": 85.0,
    }

