from django.core.mail import EmailMessage
from django.conf import settings


STANDARD_TEMPLATE = """Dear {company} Data Privacy Team,

I am writing to formally request the removal and deletion of ALL personal information you hold about me, including but not limited to any profiles, listings, records, or data that may appear on {company}'s websites or that you may sell to or share with third parties.

The information to be removed:

Full Name: {name}
Email: {email}
Phone: {phone}
Address: {address}
Date of Birth: {dob}

This request is made under:
- The California Consumer Privacy Act (CCPA) // California Privacy Rights Act (CPRA)
- General Data Protection Regulation (GDPR) if applicable
- Your company's own privacy policy terms

I request that you:
1. Remove all personal profiles or listings that appear on your services
2. Delete all my personal information from your databases
3. Cease selling, sharing, or disclosing my information to any third parties
4. Confirm completion of this request in writing

Per applicable law, please process this request without undue delay and confirm the actions taken.

Please confirm receipt of this request and let me know when my data has been removed. I expect a response within 30 days as required by law.

Thank you for your prompt attention to this matter.

Sincerely,
{name}
{email}
{phone}
"""


class EmailDeletionEngine:
    @staticmethod
    def send_request(broker, full_name, email, phone="", address="", dob=""):
        """Send a deletion request email to a broker."""
        context = {
            "company": broker.name,
            "name": full_name,
            "email": email,
            "phone": phone or "Not provided",
            "address": address or "Not provided",
            "dob": dob or "Not provided",
        }

        template = broker.email_template or STANDARD_TEMPLATE

        for key, val in context.items():
            template = template.replace("{" + key + "}", str(val))

        if not broker.opt_out_email:
            raise ValueError(f"Broker {broker.name} has no opt-out email configured")

        msg = EmailMessage(
            subject=f"Request to Delete Personal Information - {full_name} - Ref #{full_name.replace(' ', '')[:20]}",
            body=template,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[broker.opt_out_email],
        )

        msg.reply_to = [email]
        msg.send()
        return {"sent_to": broker.opt_out_email, "subject": msg.subject}

    @staticmethod
    def send_data_stop_request(broker, full_name, email, stop_selling=True, stop_sharing=True, stop_marketing=True):
        """Send a data stop / opt-out request to a broker who sells personal data."""
        stops = []
        if stop_selling:
            stops.append("sell my personal information")
        if stop_sharing:
            stops.append("share my personal information with third parties")
        if stop_marketing:
            stops.append("use my information for marketing purposes")

        stop_text = f"I request that you immediately STOP ALL of the following activities involving my personal data:\n"
        for s in stops:
            stop_text += f"  - {s}\n"

        template = f"""Dear {{company}} Privacy Team,

I am writing to formally exercise my right to opt out of the sale, sharing, and use of my personal information.

The information currently held:
Full Name: {full_name}
Email: {email}

{stop_text}
This request is made under the California Privacy Rights Act (CPRA), GDPR, and your company's privacy policy.

I will not use your services or products while my data is being sold, shared, or used for marketing. If you continue these activities, I will file a complaint with the appropriate data protection authorities.

Please confirm in writing that you have stopped the above activities and that my data will not be sold, shared, or used for marketing going forward.

Sincerely,
{full_name}
{email}
"""

        if not broker.opt_out_email:
            raise ValueError(f"Broker {broker.name} has no opt-out email configured")

        msg = EmailMessage(
            subject=f"Opt-Out Request: Stop Selling/Sharing My Data - {full_name}",
            body=template.replace("{company}", broker.name),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[broker.opt_out_email],
        )
        msg.reply_to = [email]
        msg.send()
        return {"sent_to": broker.opt_out_email, "subject": msg.subject}
