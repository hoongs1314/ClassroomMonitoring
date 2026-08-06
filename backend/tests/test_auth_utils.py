import sys
import unittest
from datetime import timedelta
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
	sys.path.insert(0, str(BACKEND_DIR))

from core.auth_utils import (
	MAX_BCRYPT_PASSWORD_BYTES,
	create_access_token,
	decode_token,
	hash_password,
	verify_password,
)


class AuthUtilsTests(unittest.TestCase):
	def test_password_hash_round_trip(self):
		password = "Classroom-Test-Password-2026"
		password_hash = hash_password(password)

		self.assertTrue(verify_password(password, password_hash))
		self.assertFalse(verify_password("wrong-password", password_hash))

	def test_rejects_password_over_bcrypt_limit(self):
		with self.assertRaises(ValueError):
			hash_password("a" * (MAX_BCRYPT_PASSWORD_BYTES + 1))

	def test_access_token_contains_required_claims(self):
		token = create_access_token(
			"42",
			extra_claims = { "roles": ["ADMIN"] },
			expires_delta = timedelta(minutes = 1),
		)
		payload = decode_token(token)

		self.assertIsNotNone(payload)
		self.assertEqual(payload["sub"], "42")
		self.assertEqual(payload["type"], "access")
		self.assertEqual(payload["roles"], ["ADMIN"])
		self.assertIn("jti", payload)
