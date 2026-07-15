from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

router = APIRouter()


LEGAL_PAGE_STYLE = """
body {
  background: #f4fafa;
  color: #183b4a;
  font-family: Inter, Arial, sans-serif;
  line-height: 1.65;
  margin: 0;
  padding: 48px 20px;
}
main {
  background: #ffffff;
  border: 1px solid #ddeeee;
  border-radius: 18px;
  box-shadow: 0 18px 50px rgba(24, 59, 74, 0.08);
  margin: 0 auto;
  max-width: 820px;
  padding: 42px;
}
h1 {
  color: #0f172a;
  font-size: 36px;
  line-height: 1.15;
  margin: 0 0 24px;
}
h2 {
  color: #183b4a;
  font-size: 20px;
  margin: 28px 0 10px;
}
p, li {
  color: #334155;
  font-size: 16px;
}
a {
  color: #0f766e;
  font-weight: 700;
}
"""


def legal_html(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{LEGAL_PAGE_STYLE}</style>
</head>
<body>
  <main>
    {body}
  </main>
</body>
</html>"""


@router.get("/privacy-policy", response_class=HTMLResponse, include_in_schema=False)
def privacy_policy():
    return legal_html(
        "ChatBot Factory Privacy Policy",
        """
<h1>ChatBot Factory Privacy Policy</h1>
<p><strong>Last updated:</strong> June 26, 2026</p>

<h2>Information We Collect</h2>
<p>
  We collect messages sent to the chatbot in order to provide automated responses,
  improve assistant quality, troubleshoot issues, and operate the ChatBot Factory platform.
</p>

<h2>How We Use Information</h2>
<p>
  Chat messages may be processed by automated assistant services to generate responses,
  retrieve relevant knowledge base content, and support conversation history for managers.
</p>

<h2>Data Sharing</h2>
<p>
  We do not sell user data. We may process data using infrastructure and AI service providers
  required to operate the chatbot service.
</p>

<h2>Data Retention</h2>
<p>
  Conversation data is retained only as needed to provide the service, debug issues,
  and help managers improve chatbot performance.
</p>

<h2>User Requests</h2>
<p>
  Users may request information, correction, or deletion of their data by contacting us.
</p>

<h2>Contact</h2>
<p>
  For privacy questions contact:
  <a href="mailto:balkis.sekri@esprit.tn">balkis.sekri@esprit.tn</a>
</p>
""",
    )


@router.head("/privacy-policy", include_in_schema=False)
def privacy_policy_head():
    return Response(status_code=200, media_type="text/html")


@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
def terms_of_service():
    return legal_html(
        "ChatBot Factory Terms of Service",
        """
<h1>ChatBot Factory Terms of Service</h1>
<p><strong>Last updated:</strong> June 26, 2026</p>

<p>
  ChatBot Factory provides tools for creating, testing, and deploying AI chatbot assistants.
  By using the service, users agree to use it lawfully and responsibly.
</p>

<h2>Acceptable Use</h2>
<p>
  Users must not use the platform to send harmful, illegal, abusive, or misleading content.
</p>

<h2>Service Availability</h2>
<p>
  The platform may be updated or interrupted for maintenance, testing, or infrastructure changes.
</p>

<h2>Contact</h2>
<p>
  For questions contact:
  <a href="mailto:balkis.sekri@esprit.tn">balkis.sekri@esprit.tn</a>
</p>
""",
    )


@router.head("/terms", include_in_schema=False)
def terms_of_service_head():
    return Response(status_code=200, media_type="text/html")


@router.get("/data-deletion", response_class=HTMLResponse, include_in_schema=False)
def data_deletion():
    return legal_html(
        "ChatBot Factory Data Deletion Instructions",
        """
<h1>ChatBot Factory Data Deletion Instructions</h1>
<p><strong>Last updated:</strong> June 26, 2026</p>

<p>
  To request deletion of chatbot conversation data or related user data, send an email to
  <a href="mailto:balkis.sekri@esprit.tn">balkis.sekri@esprit.tn</a>.
</p>

<p>
  Please include the phone number, email address, or conversation identifier related to the
  request so we can locate the relevant records.
</p>

<p>
  We will review and process deletion requests as soon as reasonably possible.
</p>
""",
    )


@router.head("/data-deletion", include_in_schema=False)
def data_deletion_head():
    return Response(status_code=200, media_type="text/html")
