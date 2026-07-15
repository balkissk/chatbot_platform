import unittest

from fastapi import HTTPException

from main import app
from routes.channel_routes import clean_channel_type


class ChannelRemovalTests(unittest.TestCase):
    def test_meta_whatsapp_and_messenger_routes_are_not_registered(self):
        route_paths = {getattr(route, "path", "") for route in app.routes}
        joined_paths = "\n".join(sorted(route_paths)).lower()

        self.assertNotIn("whatsapp", joined_paths)
        self.assertNotIn("messenger", joined_paths)
        self.assertNotIn("/channels/whatsapp/oauth", joined_paths)
        self.assertNotIn("debug-meta", joined_paths)

    def test_only_supported_channels_are_accepted(self):
        self.assertEqual(clean_channel_type("web"), "web")
        self.assertEqual(clean_channel_type("widget"), "widget")
        self.assertEqual(clean_channel_type("api"), "api")

        for channel in ("whatsapp", "messenger"):
            with self.subTest(channel=channel):
                with self.assertRaises(HTTPException) as raised:
                    clean_channel_type(channel)
                self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
