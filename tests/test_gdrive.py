import json
from unittest.mock import MagicMock
import pytest
import gdrive

class TestClientConfig:
    def test_is_configured_false_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(gdrive, '_APP_DIR', tmp_path / 'nonexistent1')
        monkeypatch.setattr(gdrive, 'TOKEN_DIR', tmp_path / 'nonexistent2')
        assert gdrive.is_configured() is False

    def test_is_configured_true_when_file_exists(self, monkeypatch, tmp_path):
        config_dir = tmp_path / 'app_dir'
        config_dir.mkdir()
        config_file = config_dir / 'client_config.json'
        config_file.write_text(json.dumps({'installed': {'client_id': '123'}}))
        monkeypatch.setattr(gdrive, '_APP_DIR', config_dir)
        monkeypatch.setattr(gdrive, 'TOKEN_DIR', tmp_path / 'nonexistent')
        assert gdrive.is_configured() is True

    def test_load_client_config_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(gdrive, '_APP_DIR', tmp_path)
        monkeypatch.setattr(gdrive, 'TOKEN_DIR', tmp_path / 'tokens')
        with pytest.raises(FileNotFoundError):
            gdrive._load_client_config()

    def test_load_client_config_invalid_format(self, monkeypatch, tmp_path):
        cfg = tmp_path / 'client_config.json'
        cfg.write_text(json.dumps({'invalid_key': 'value'}))
        monkeypatch.setattr(gdrive, '_APP_DIR', tmp_path)
        monkeypatch.setattr(gdrive, 'TOKEN_DIR', tmp_path / 'tokens')
        with pytest.raises(ValueError):
            gdrive._load_client_config()

    def test_load_client_config_valid(self, monkeypatch, tmp_path):
        cfg = tmp_path / 'client_config.json'
        payload = {'installed': {'client_id': 'abc', 'client_secret': 'secret'}}
        cfg.write_text(json.dumps(payload))
        monkeypatch.setattr(gdrive, '_APP_DIR', tmp_path)
        monkeypatch.setattr(gdrive, 'TOKEN_DIR', tmp_path / 'tokens')
        assert gdrive._load_client_config() == payload

class TestLogout:
    def test_logout_removes_token(self, monkeypatch, tmp_path):
        token_file = tmp_path / 'gdrive_token.json'
        token_file.write_text(json.dumps({'token': 'xyz'}))
        monkeypatch.setattr(gdrive, 'TOKEN_PATH', token_file)
        assert token_file.exists()
        gdrive.logout()
        assert not token_file.exists()

    def test_logout_missing_ok(self, monkeypatch, tmp_path):
        token_file = tmp_path / 'nonexistent_token.json'
        monkeypatch.setattr(gdrive, 'TOKEN_PATH', token_file)
        gdrive.logout()

class TestServiceHelpers:
    def test_get_user_email(self):
        mock_service = MagicMock()
        mock_about = MagicMock()
        mock_service.about.return_value = mock_about
        mock_about.get.return_value.execute.return_value = {'user': {'emailAddress': 'test@example.com'}}
        assert gdrive.get_user_email(mock_service) == 'test@example.com'

    def test_get_user_email_error(self):
        mock_service = MagicMock()
        mock_service.about.side_effect = Exception('API Error')
        assert gdrive.get_user_email(mock_service) == ""

    def test_list_folder(self):
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_service.files.return_value = mock_files
        mock_files.list.return_value.execute.return_value = {'files': [{'id': 'f1', 'name': 'export.zip'}]}
        res = gdrive.list_folder(mock_service)
        assert len(res) == 1
        assert res[0]['name'] == 'export.zip'
