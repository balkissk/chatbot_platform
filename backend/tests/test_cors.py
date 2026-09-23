import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from main import (
    FastPreflightCORSMiddleware,
    PublicWidgetCORSMiddleware,
    allowed_origins,
    app as main_app,
    parse_allowed_origins,
    parse_public_allowed_origins,
    public_widget_allowed_origins,
)


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

    def test_public_origins_can_use_wildcard_for_credentialless_widget_paths(self):
        self.assertEqual(parse_public_allowed_origins("*"), ["*"])
        self.assertEqual(parse_public_allowed_origins('["*"]'), ["*"])

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

    def test_fast_preflight_handles_login_before_inner_app(self):
        app = FastAPI()
        calls = {"inner": 0, "login": 0}

        @app.middleware("http")
        async def count_inner_calls(request, call_next):
            calls["inner"] += 1
            return await call_next(request)

        @app.post("/auth/login")
        def login():
            calls["login"] += 1
            return {"ok": True}

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://frontend.azurewebsites.net"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.add_middleware(
            FastPreflightCORSMiddleware,
            allowed_credentialed_origins=["https://frontend.azurewebsites.net"],
            allowed_public_origins=[],
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
        self.assertEqual(response.headers["access-control-allow-methods"], "POST")
        self.assertEqual(response.headers["access-control-allow-headers"], "content-type")
        self.assertEqual(calls, {"inner": 0, "login": 0})

    def test_fast_preflight_does_not_allow_unconfigured_dashboard_origin(self):
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://frontend.azurewebsites.net"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.add_middleware(
            FastPreflightCORSMiddleware,
            allowed_credentialed_origins=["https://frontend.azurewebsites.net"],
            allowed_public_origins=[],
        )

        client = TestClient(app)
        response = client.options(
            "/auth/login",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.headers.get("access-control-allow-origin"), "https://evil.example")

    def test_public_widget_defaults_include_external_local_development_origins(self):
        with patch.dict(
            "os.environ",
            {
                "ENVIRONMENT": "development",
                "PUBLIC_WIDGET_ALLOWED_ORIGINS": "",
                "PUBLIC_CHAT_ALLOWED_ORIGINS": "",
            },
        ):
            origins = public_widget_allowed_origins()

        self.assertIn("http://localhost:5500", origins)
        self.assertIn("http://127.0.0.1:5500", origins)
        self.assertIn("http://localhost:4200", origins)

    def test_public_widget_preflight_allows_external_origin_without_credentials(self):
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:4200"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.add_middleware(
            PublicWidgetCORSMiddleware,
            allowed_public_origins=["http://localhost:5500"],
        )

        client = TestClient(app)
        response = client.options(
            "/public/chat/stream",
            headers={
                "Origin": "http://localhost:5500",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5500")
        self.assertNotIn("access-control-allow-credentials", response.headers)
        self.assertIn("POST", response.headers["access-control-allow-methods"])
        self.assertEqual(response.headers["access-control-allow-headers"], "content-type")

    def test_public_widget_cors_does_not_open_dashboard_preflight(self):
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:4200"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.add_middleware(
            PublicWidgetCORSMiddleware,
            allowed_public_origins=["http://localhost:5500"],
        )

        client = TestClient(app)
        response = client.options(
            "/auth/login",
            headers={
                "Origin": "http://localhost:5500",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5500")

    def test_public_widget_actual_response_does_not_allow_credentials(self):
        app = FastAPI()

        @app.post("/public/chat/stream")
        def stream():
            return {"ok": True}

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:4200"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.add_middleware(
            PublicWidgetCORSMiddleware,
            allowed_public_origins=["http://localhost:5500"],
        )

        client = TestClient(app)
        response = client.post(
            "/public/chat/stream",
            headers={"Origin": "http://localhost:5500"},
            json={"message": "hello"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5500")
        self.assertNotIn("access-control-allow-credentials", response.headers)

    def test_main_app_allows_local_external_widget_stream_preflight(self):
        client = TestClient(main_app)
        response = client.options(
            "/public/chat/stream",
            headers={
                "Origin": "http://localhost:5500",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5500")


if __name__ == "__main__":
    unittest.main()
