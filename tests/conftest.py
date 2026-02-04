"""
Pytest fixtures for Culture tests.
"""
import pytest
import base64
from nacl.signing import SigningKey

from app import create_app
from app.extensions import db
from app.models import agent_store


@pytest.fixture
def app():
    """Create application for testing."""
    app = create_app({
        'TESTING': True,
        'CHALLENGE_EXPIRY': 300,
        'TIMESTAMP_TOLERANCE': 60,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'BASE_URL': 'https://join-the-culture.com',
    })

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_store(app):
    """Clear agent store before each test."""
    agent_store.clear_challenges()
    with app.app_context():
        # Clear all agents from database
        from app.models import Agent
        Agent.query.delete()
        db.session.commit()
    yield
    agent_store.clear_challenges()


@pytest.fixture
def keypair():
    """Generate a test Ed25519 keypair."""
    signing_key = SigningKey.generate()
    private_key_b64 = base64.b64encode(signing_key.encode()).decode()
    public_key_b64 = base64.b64encode(signing_key.verify_key.encode()).decode()

    return {
        'signing_key': signing_key,
        'private_key_b64': private_key_b64,
        'public_key_b64': public_key_b64,
    }


@pytest.fixture
def registered_agent(client, keypair):
    """Create and register an agent, return agent info with keys."""
    # Step 1: Request challenge
    resp = client.post('/register',
        json={'public_key': keypair['public_key_b64'], 'name': 'Test Agent'},
        content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    challenge = data['challenge']

    # Step 2: Sign and verify
    signature = keypair['signing_key'].sign(challenge.encode()).signature
    signature_b64 = base64.b64encode(signature).decode()

    resp = client.post('/register/verify',
        json={'public_key': keypair['public_key_b64'], 'signature': signature_b64},
        content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()

    return {
        **keypair,
        'agent_id': data['agent_id'],
        'name': 'Test Agent',
    }


def make_auth_headers(keypair, method: str, path: str, body: str = "") -> dict:
    """Create authentication headers for a request."""
    import time

    timestamp = str(int(time.time()))
    message = f"{timestamp}:{method}:{path}:{body}"

    signature = keypair['signing_key'].sign(message.encode()).signature
    signature_b64 = base64.b64encode(signature).decode()

    return {
        'X-Agent-Key': keypair['public_key_b64'],
        'X-Timestamp': timestamp,
        'X-Signature': signature_b64,
    }
