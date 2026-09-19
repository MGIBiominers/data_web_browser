from unittest import mock

import s3_clients


class TestDefaultClient:
    def test_returns_s3_client(self):
        mock_client = mock.MagicMock()
        with mock.patch('s3_clients.boto3') as mock_boto3:
            mock_boto3.client.return_value = mock_client

            result = s3_clients.default_client()

            mock_boto3.client.assert_called_once_with("s3", region_name=s3_clients._REGION)
            assert result is mock_client
