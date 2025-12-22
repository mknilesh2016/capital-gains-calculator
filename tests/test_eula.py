"""
Unit tests for EULA functionality in main.py.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
from datetime import datetime


class TestEULAFunctions:
    """Tests for EULA acceptance functions."""
    
    @pytest.fixture
    def temp_eula_dir(self):
        """Create a temporary directory for EULA config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "eula_accepted"
    
    def test_check_eula_not_accepted(self, temp_eula_dir):
        """Test EULA check when not accepted."""
        from main import check_eula_accepted, EULA_CONFIG_FILE
        
        # Patch the config file path to use temp dir
        with patch('main.EULA_CONFIG_FILE', temp_eula_dir):
            assert check_eula_accepted() is False
    
    def test_check_eula_accepted(self, temp_eula_dir):
        """Test EULA check when previously accepted."""
        from main import check_eula_accepted, save_eula_acceptance
        
        with patch('main.EULA_CONFIG_FILE', temp_eula_dir):
            # Create the acceptance file
            temp_eula_dir.parent.mkdir(parents=True, exist_ok=True)
            temp_eula_dir.write_text(f"accepted={datetime.now().isoformat()}")
            
            assert check_eula_accepted() is True
    
    def test_save_eula_acceptance(self, temp_eula_dir):
        """Test saving EULA acceptance."""
        from main import save_eula_acceptance
        
        with patch('main.EULA_CONFIG_FILE', temp_eula_dir):
            save_eula_acceptance()
            
            assert temp_eula_dir.exists()
            content = temp_eula_dir.read_text()
            assert "accepted=" in content
    
    def test_prompt_eula_acceptance_accept(self, temp_eula_dir, capsys):
        """Test EULA prompt when user accepts."""
        from main import prompt_eula_acceptance
        
        with patch('main.EULA_CONFIG_FILE', temp_eula_dir):
            with patch('builtins.input', return_value='ACCEPT'):
                result = prompt_eula_acceptance()
                
                assert result is True
                assert temp_eula_dir.exists()
                
                captured = capsys.readouterr()
                assert "EULA accepted" in captured.out
    
    def test_prompt_eula_acceptance_lowercase_accept(self, temp_eula_dir):
        """Test EULA prompt accepts lowercase 'accept'."""
        from main import prompt_eula_acceptance
        
        with patch('main.EULA_CONFIG_FILE', temp_eula_dir):
            with patch('builtins.input', return_value='accept'):
                result = prompt_eula_acceptance()
                assert result is True
    
    def test_prompt_eula_acceptance_reject(self, temp_eula_dir, capsys):
        """Test EULA prompt when user rejects."""
        from main import prompt_eula_acceptance
        
        with patch('main.EULA_CONFIG_FILE', temp_eula_dir):
            with patch('builtins.input', return_value='NO'):
                result = prompt_eula_acceptance()
                
                assert result is False
                assert not temp_eula_dir.exists()
                
                captured = capsys.readouterr()
                assert "not accepted" in captured.out
    
    def test_prompt_eula_keyboard_interrupt(self, temp_eula_dir, capsys):
        """Test EULA prompt handles Ctrl+C gracefully."""
        from main import prompt_eula_acceptance
        
        with patch('main.EULA_CONFIG_FILE', temp_eula_dir):
            with patch('builtins.input', side_effect=KeyboardInterrupt):
                result = prompt_eula_acceptance()
                
                assert result is False
                
                captured = capsys.readouterr()
                assert "cancelled" in captured.out
    
    def test_eula_text_content(self):
        """Test EULA text contains required sections."""
        from main import EULA_TEXT
        
        # Verify key sections are present
        assert "NON-COMMERCIAL USE" in EULA_TEXT
        assert "NO WARRANTY" in EULA_TEXT
        assert "NOT PROFESSIONAL TAX ADVICE" in EULA_TEXT
        assert "TAX RATE ASSUMPTIONS" in EULA_TEXT
        assert "LIMITATION OF LIABILITY" in EULA_TEXT
        assert "USER RESPONSIBILITY" in EULA_TEXT


class TestCommandLineFlags:
    """Tests for EULA-related command line flags."""
    
    def test_show_eula_flag_present(self):
        """Test --show-eula flag is defined."""
        from main import create_argument_parser
        
        parser = create_argument_parser()
        args = parser.parse_args(['--show-eula'])
        
        assert args.show_eula is True
    
    def test_reset_eula_flag_present(self):
        """Test --reset-eula flag is defined."""
        from main import create_argument_parser
        
        parser = create_argument_parser()
        args = parser.parse_args(['--reset-eula'])
        
        assert args.reset_eula is True
    
    def test_default_flags_false(self):
        """Test EULA flags are False by default."""
        from main import create_argument_parser
        
        parser = create_argument_parser()
        args = parser.parse_args([])
        
        assert args.show_eula is False
        assert args.reset_eula is False

