import json
import os
import sys
from unittest import mock

import pytest

sys.modules['boto3'] = mock.MagicMock()

import s3_clients


class TestDefaultClient:
    def test_returns_s3_client(self):
        mock_client = mock.MagicMock()
        with mock.patch('s3_clients.boto3') as mock_boto3:
            mock_boto3.client.return_value = mock_client
            
            result = s3_clients.default_client()
            
            mock_boto3.client.assert_called_once_with("s3", region_name=s3_clients._REGION)
            assert result is mock_client


class TestPresignClient:
    def setup_method(self):
        s3_clients._presign_client = None
    
    def test_fetches_credentials_from_ssm_on_first_call(self):
        creds = {
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
        
        with mock.patch.dict(os.environ, {"PRESIGN_CREDENTIALS_PARAM": "my-param"}):
            with mock.patch('s3_clients.boto3') as mock_boto3:
                mock_ssm = mock.MagicMock()
                mock_s3 = mock.MagicMock()
                
                def client_factory(service, **kwargs):
                    return mock_ssm if service == "ssm" else mock_s3
                
                mock_boto3.client.side_effect = client_factory
                mock_ssm.get_parameter.return_value = {
                    "Parameter": {"Value": json.dumps(creds)}
                }
                
                result = s3_clients.presign_client()
                
                mock_ssm.get_parameter.assert_called_once_with(
                    Name="my-param",
                    WithDecryption=True
                )
                assert result is mock_s3
    
    def test_returns_cached_client_on_subsequent_calls(self):
        creds = {
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
        
        with mock.patch.dict(os.environ, {"PRESIGN_CREDENTIALS_PARAM": "my-param"}):
            with mock.patch('s3_clients.boto3') as mock_boto3:
                mock_ssm = mock.MagicMock()
                mock_s3 = mock.MagicMock()
                
                def client_factory(service, **kwargs):
                    return mock_ssm if service == "ssm" else mock_s3
                
                mock_boto3.client.side_effect = client_factory
                mock_ssm.get_parameter.return_value = {
                    "Parameter": {"Value": json.dumps(creds)}
                }
                
                result1 = s3_clients.presign_client()
                result2 = s3_clients.presign_client()
                
                mock_ssm.get_parameter.assert_called_once()
                assert result1 is result2
                assert result1 is mock_s3
    
    def test_s3_client_created_with_correct_credentials(self):
        creds = {
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
        
        with mock.patch.dict(os.environ, {"PRESIGN_CREDENTIALS_PARAM": "my-param"}):
            with mock.patch('s3_clients.boto3') as mock_boto3:
                mock_ssm = mock.MagicMock()
                mock_s3 = mock.MagicMock()
                
                def client_factory(service, **kwargs):
                    return mock_ssm if service == "ssm" else mock_s3
                
                mock_boto3.client.side_effect = client_factory
                mock_ssm.get_parameter.return_value = {
                    "Parameter": {"Value": json.dumps(creds)}
                }
                
                s3_clients.presign_client()
                
                s3_calls = [
                    call for call in mock_boto3.client.call_args_list
                    if call[0][0] == "s3"
                ]
                assert len(s3_calls) >= 1
                
                s3_call_kwargs = s3_calls[-1][1]
                assert s3_call_kwargs["aws_access_key_id"] == "AKIAIOSFODNN7EXAMPLE"
                assert s3_call_kwargs["aws_secret_access_key"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    def test_presign_client_forces_virtual_addressing_style(self):
        """Confirmed the hard way against the real deployed bucket: without
        this, generate_presigned_url() builds a URL against the legacy
        global s3.amazonaws.com host even with the right region_name set,
        which then 307-redirects and breaks the query-string signature.
        See s3_clients.py's module docstring for the full story."""
        creds = {
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }

        with mock.patch.dict(os.environ, {"PRESIGN_CREDENTIALS_PARAM": "my-param"}):
            with mock.patch('s3_clients.boto3') as mock_boto3:
                mock_ssm = mock.MagicMock()
                mock_s3 = mock.MagicMock()

                def client_factory(service, **kwargs):
                    return mock_ssm if service == "ssm" else mock_s3

                mock_boto3.client.side_effect = client_factory
                mock_ssm.get_parameter.return_value = {
                    "Parameter": {"Value": json.dumps(creds)}
                }

                s3_clients.presign_client()

                s3_calls = [
                    call for call in mock_boto3.client.call_args_list
                    if call[0][0] == "s3"
                ]
                config = s3_calls[-1][1]["config"]
                assert config.s3["addressing_style"] == "virtual"

    def test_ssm_parameter_fetch_error_propagates(self):
        with mock.patch.dict(os.environ, {"PRESIGN_CREDENTIALS_PARAM": "my-param"}):
            with mock.patch('s3_clients.boto3') as mock_boto3:
                mock_ssm = mock.MagicMock()
                mock_boto3.client.return_value = mock_ssm
                mock_ssm.get_parameter.side_effect = Exception("ParameterNotFound")
                
                with pytest.raises(Exception, match="ParameterNotFound"):
                    s3_clients.presign_client()
    
    def test_invalid_json_credentials_raises_json_error(self):
        with mock.patch.dict(os.environ, {"PRESIGN_CREDENTIALS_PARAM": "my-param"}):
            with mock.patch('s3_clients.boto3') as mock_boto3:
                mock_ssm = mock.MagicMock()
                mock_boto3.client.return_value = mock_ssm
                mock_ssm.get_parameter.return_value = {
                    "Parameter": {"Value": "{invalid json"}
                }
                
                with pytest.raises(json.JSONDecodeError):
                    s3_clients.presign_client()
    
    def test_missing_credential_fields_raises_key_error(self):
        creds = {"access_key_id": "AKIAIOSFODNN7EXAMPLE"}
        
        with mock.patch.dict(os.environ, {"PRESIGN_CREDENTIALS_PARAM": "my-param"}):
            with mock.patch('s3_clients.boto3') as mock_boto3:
                mock_ssm = mock.MagicMock()
                mock_boto3.client.return_value = mock_ssm
                mock_ssm.get_parameter.return_value = {
                    "Parameter": {"Value": json.dumps(creds)}
                }
                
                with pytest.raises(KeyError):
                    s3_clients.presign_client()