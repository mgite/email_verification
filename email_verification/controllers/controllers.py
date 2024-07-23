# -*- coding: utf-8 -*-
from odoo import http, tools, Command, _
from odoo.http import request

PARTNER_EMAIL_VERIFICATION_PARAMS = ["token", "email", "id"]


class EmailVerification(http.Controller):
    @http.route("/partner/identity/verification", type="http", auth="public", website=True, sitemap=False)
    def partner_identity_verification(self, *args, **kw):
        qcontext = {k: v for (k, v) in request.params.items() if k in PARTNER_EMAIL_VERIFICATION_PARAMS}
        message = ""
        if not qcontext:
            message = _("Missing parameters")
        else:
            if qcontext.get("token") and qcontext.get("email") and qcontext.get("id"):
                found_partner = (
                    request.env["res.partner"]
                    .sudo()
                    .search(
                        [
                            ("email", "=", qcontext.get("email")),
                            ("id", "=", qcontext.get("id")),
                            ("partner_email_verification_token", "=", qcontext.get("token")),
                        ],
                        limit=1,
                    )
                )
                if found_partner:
                    if not found_partner.partner_identity_verification:
                        found_partner.sudo().write(
                            {
                                "partner_identity_verification": True,
                                "partner_email_verification_token": False,
                                "partner_identity_verification_ids": [
                                    Command.create({"email": qcontext.get("email"), "email_is_verified": True})
                                ],
                            }
                        )
                        found_partner.message_post(body=f"Your email is successfully verified.")
                        message = _("Your email address has been successfully verified.")
                    else:
                        message = _("Your email address is already verified.")
                else:
                    message = _("Partner not found.")
            else:
                message = _("Missing parameters")
        return http.request.render(
            "email_verification.email_verification_page",
            {
                "message": message,
            },
        )
