import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from main import allowed_origins, parse_allowed_origins


class CorsConfigurationTest(unittest.TestCase):
    def test_allowed_origins_accepts_comma_separated_values(self):
        origins = parse_allowed_origins("https://frontend.azurewebsites.net, http://localhost:4200/")

        self.assertEqual(
            origins,
            ["https://frontend.azurewebsites.net", "http://localhost:4200"],
        )

    def test_allowed_origins_accepts_json_list_values(self):
        origins = parse_allowed_origins('["https://frontend.azurewebsites.net", "http://127.0.0.1:4200/"]')

        self.assertEqual(
            origins,
            ["https://frontend.azurewebsites.net", "http://127.0.0.1:4200"],
        )

    def test_wildcard_origin_is_rejected_when_credentials_are_enabled(self):
        with self.assertRaises(ValueError):
            parse_allowed_origins("*")

    def test_defaults_preserve_localhost_development_origins(self):
        self.assertIn("http://localhost:4200", allowed_origins())
        self.assertIn("http://127.0.0.1:4200", allowed_origins())

    def test_frontend_base_url_can_configure_production_origin(self):
        with patch.dict(
            "os.environ",
            {
                "ALLOWED_ORIGINS": "",
                "FRONTEND_URL": "",
                "FRONTEND_BASE_URL": "https://frontend.azurewebsites.net/",
            },
        ):
            self.assertEqual(allowed_origins(), ["https://frontend.azurewebsites.net"])

    def test_cors_middleware_handles_login_preflight(self):
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://frontend.azurewebsites.net"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        client = TestClient(app)
        response = client.options(
            "/auth/login",
            headers={
                "Origin": "https://frontend.azurewebsites.net",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "https://frontend.azurewebsites.net")
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")


if __name__ == "__main__":
    unittest.main()
