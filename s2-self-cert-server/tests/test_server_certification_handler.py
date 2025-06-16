import asyncio
import base64
from src.certifier import ServerSideCertificationHandler

from testsuites.envelope_models import (
    ServerMessageEnvelope,
    CertificationEnvelope,
    CertificationMessageType,
    KeyRegistrationRequestMessage,
    ChallengeMessage,
    ChallengeProofMessage,
    ChallengeStatusMessage,
    CertificationMessage,
    parse_certification_message,
)
from unittest.mock import AsyncMock

import base64
import pytest


@pytest.mark.asyncio
async def test_handler(mocker):
    mock_signer = mocker.Mock()
    mock_key_repository = mocker.Mock()
    mock_channel = mocker.Mock()

    # Make the send method async
    mock_channel.send = AsyncMock()

    client_id = "client"
    pub_key = "some key"

    handler = ServerSideCertificationHandler(mock_signer, mock_key_repository)

    key_reg_message = KeyRegistrationRequestMessage(
        public_key=pub_key, client_id=client_id
    )

    await handler.handle_key_registration_request(key_reg_message, mock_channel)

    # Verify channel.send was called once
    mock_channel.send.assert_called_once()

    # Get the actual argument passed to send()
    call_args = mock_channel.send.call_args[0][0]

    # Verify it's a CertificationEnvelope with ChallengeMessage
    assert isinstance(call_args, CertificationEnvelope)
    assert isinstance(call_args.message, ChallengeMessage)

    # Verify the challenge bytes are correctly encoded

    # Verify handler state was updated correctly
    assert handler.client_id == client_id
    assert handler.public_key_pem == pub_key
    assert handler.challenge_bytes is not None

    # Verify the event was set
    assert handler._challenge_sent_event.is_set()


@pytest.mark.asyncio
async def test_handle_challenge_proof_success(mocker):
    mock_signer = mocker.Mock()
    mock_key_repository = mocker.Mock()
    mock_channel = mocker.Mock()

    mock_channel.send = AsyncMock()

    handler = ServerSideCertificationHandler(mock_signer, mock_key_repository)

    # Set up handler state (normally done by handle_key_registration_request)
    handler.client_id = "test_client"
    handler.public_key_pem = "test_public_key"
    handler.challenge_bytes = b"test_challenge"

    # Mock the signer methods
    mock_public_key = mocker.Mock()
    mock_signer.load_public_key_from_pem.return_value = mock_public_key
    mock_signer.verify_bytes.return_value = True

    # Create test message
    test_signature = base64.b64encode(b"test_signature").decode("ascii")
    proof_message = ChallengeProofMessage(signature=test_signature)

    await handler.handle_challenge_proof(proof_message, mock_channel)

    # Verify signer methods were called correctly
    mock_signer.load_public_key_from_pem.assert_called_once_with("test_public_key")
    mock_signer.verify_bytes.assert_called_once_with(
        b"test_signature", b"test_challenge", mock_public_key
    )

    # Verify key was stored
    mock_key_repository.store_key.assert_called_once_with(
        "test_client", "test_public_key"
    )

    # Verify response was sent
    mock_channel.send.assert_called_once()
    call_args = mock_channel.send.call_args[0][0]
    assert isinstance(call_args, CertificationEnvelope)
    assert isinstance(call_args.message, ChallengeStatusMessage)
    assert call_args.message.success is True
    assert call_args.message.message == "Challenge Successful"

    # Verify handler state
    assert handler.challenge_status is True
    assert handler._challenge_complete_event.is_set()
